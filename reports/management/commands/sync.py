import datetime
import json
import time
import traceback

from django.core import exceptions
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jetere import jenkins
from reports import models
from . import configure

# TODO: should be configurable in DB (maybe per job).
BUILDS_HISTORY_LIMIT = 20


class Command(BaseCommand):
    help = 'Sync database with Jenkins'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--every',
                            type=int,
                            help='Sync periodically every X seconds.')
        parser.add_argument('--max-builds',
                            type=int,
                            default=BUILDS_HISTORY_LIMIT,
                            help='Maximum number of builds to retrieve.')

    @staticmethod
    def _extract_started_by(jenkins_build):
        actions = jenkins_build.get('actions', [])
        for action in actions:
            causes = action.get('causes', [])
            for cause in causes:
                description = cause['shortDescription']
                if 'Started by timer' in description:
                    return 'Timer'
                elif 'Started by' in description:
                    return description.replace('Started by user', '').strip()
        return None

    @staticmethod
    def _process_build_tests(raw_test_report, build):
        suites = raw_test_report.get('suites', [])
        tests_count = 0
        for suite in suites:
            # TODO: try except
            cases = suite.get('cases', [])
            for case in cases:
                test = models.Test()
                test.duration = datetime.timedelta(
                        seconds=int(case['duration']))
                test.class_name = case['className']
                test.status = case['status']
                test.name = case['name']
                test.build_id = build.id
                test.save()
                tests_count += 1

                models.TestLogs(
                    test_id=test.id,
                    error_stack_trace=case['errorStackTrace'],
                    stdout=case['stdout'],
                    stderr=case['stderr'],
                    error_details=case['errorDetails']
                ).save()

        return tests_count

    @staticmethod
    def _get_jenkins_configuration():
        configuration = models.Configuration.objects.all()
        if len(configuration) == 0:
            from_file = configure.load_jenkins_configuration_from_file()
            if not from_file:
                raise CommandError('Jenkins configuration not found in DB.')
            else:
                return configure.update_jenkins_configuration_in_db(from_file)
        if len(configuration) > 1:
            raise CommandError('There is more than one Jenkins configuration '
                               'in DB. remove unused configurations.')
        return configuration[0]

    def handle(self, *args, **options):
        every = options.get('every', None)
        max_builds = options['max_builds']
        if every:
            while True:
                self.do_sync(max_builds)
                self.stdout.write('-----')
                self.stdout.write(
                        'Next sync will occur in %d seconds.' % every)
                self.stdout.write('')
                time.sleep(every)
        else:
            self.do_sync(max_builds)

    def do_sync(self, max_builds):
        start_time = time.time()
        self.stdout.write('*********')
        self.stdout.write('* Syncing from Jenkins...')
        self.stdout.write('')
        config = self._get_jenkins_configuration()
        self.stdout.write(
                self.style.SUCCESS('Jenkins configuration found in DB.'))
        self.stdout.write('Jenkins URL: %s' % config.jenkins_url)
        self.stdout.write('Jenkins username: %s, password: *****'
                          % config.jenkins_username)
        # TODO: rest call for verifying jenkins connectivity
        self.stdout.write(self.style.SUCCESS(
                'Connection to Jenkins server established.'))
        jobs = models.Job.objects.all()
        errors = []
        self.stdout.write('The following jobs will be processed:')
        for job in jobs:
            self.stdout.write(' - %s' % job)
        for job in jobs:
            self.stdout.write('')
            self.stdout.write('** Processing job: %s' % job)
            server = jenkins.Jenkins(config.jenkins_url,
                                     config.jenkins_username,
                                     config.jenkins_password)
            try:
                jenkins_job = server.get_job(job.jenkins_path,
                                             tree='displayName,builds[number]')
                display_name = jenkins_job['displayName']
                jenkins_builds = [x['number'] for x in jenkins_job['builds']]
                if job.name != display_name:
                    job.name = display_name
                    job.save()
                    self.stdout.write('Updated job.id=%d name to "%s"'
                                      % (job.id, display_name))

                # update in progress builds
                in_progress_builds = models.Build.objects.filter(job_id=job.id,
                                                                 building=True)
                self.stdout.write('Found in progress builds: %s'
                                  % json.dumps(
                        [x.number for x in in_progress_builds]))
                if in_progress_builds:
                    self.stdout.write('Processing in progress builds..')
                    for build in in_progress_builds:
                        self._process_build(
                                build.number, errors, job, server, update=True)

                builds_to_update = []
                for build_number in jenkins_builds[:max_builds]:
                    try:
                        models.Build.objects.get(job_id=job.id,
                                                 number=build_number)
                    except exceptions.ObjectDoesNotExist:
                        builds_to_update.append(build_number)
                self.stdout.write(
                        'The following new builds will be synced from '
                        'jenkins: %s' % json.dumps(builds_to_update))

                for build_number in builds_to_update:
                    self._process_build(build_number, errors, job, server)

            except Exception as e:
                errors.append('Error processing job [%s]: %s - %s'
                              % (job, e.__class__.__name__, e.message))
                self.stdout.write(self.style.ERROR(errors[-1]))
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
            sync_data = models.Sync.objects.all()
            if sync_data:
                sync_data = sync_data[0]
            else:
                sync_data = models.Sync()
            sync_data.last_update = timezone.make_aware(
                    datetime.datetime.now())
            sync_data.save()

        # TODO: store errors in DB.
        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors summary:'))
            for error in errors:
                self.stdout.write('- %s' % error)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
                'Sync done in %s seconds.' % (time.time() - start_time)))

    def _process_build(self, build_number, errors, job, server, update=False):
        self.stdout.write('\nProcessing build #%d..' % build_number)
        try:
            # TODO: add tree=... to get_build invocation
            jenkins_build = server.get_build(job.jenkins_path,
                                             build_number)
            if update:
                build = models.Build.objects.get(job_id=job.id,
                                                 number=build_number)
            else:
                build = models.Build()
            duration = datetime.timedelta(
                    milliseconds=jenkins_build['duration'])
            build.duration = duration - datetime.timedelta(microseconds=duration.microseconds)
            build.number = build_number
            build.result = jenkins_build['result']

            build.timestamp = timezone.make_aware(
                    datetime.datetime.fromtimestamp(
                            int(jenkins_build['timestamp']) / 1000),
                    timezone.get_current_timezone())

            build.started_by = self._extract_started_by(jenkins_build)
            build.building = jenkins_build['building']
            build.job = job
            build.save()

            build = models.Build.objects.get(job_id=job.id,
                                             number=build.number)
            self.stdout.write('Build result: ' + str(build.result))

            if build.building:
                self.stdout.write(' - Build in "building" state, '
                                  'not processing tests.')

            elif build.result == 'ABORTED':
                self.stdout.write(' - Build in "aborted" state, not processing tests.')

            else:
                report = server.get_tests_report(job.jenkins_path,
                                                 build.number)
                tests_count = self._process_build_tests(report, build)
                self.stdout.write(' - Added %d tests.' % tests_count)

        except Exception as e:
            errors.append(
                    'Error processing build number %d for job [%s]: '
                    '%s - %s' % (build_number,
                                 job,
                                 e.__class__.__name__,
                                 e.message))
            self.stdout.write(self.style.ERROR(errors[-1]))
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
