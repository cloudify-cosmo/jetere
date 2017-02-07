
import datetime
import json
import logging
import math
import os

import requests

from django.utils import timezone

from reports.config import instance as config
from reports import cache

PASSED_STRINGS = ('PASSED', 'FIXED', 'SUCCESS')
FAILED_STRINGS = ('FAILED', 'REGRESSION', 'FAILURE')
SKIPPED_STRING = 'SKIPPED'

TIMER_USER = 'Timer'
SCM_CHANGE = 'SCM Change'
BUILD_FLOW = 'Build Flow'


# TODO: redirect to an error page if jenkins is not accessible.
# TODO: cache the knowledge of no testReports for builds as otherwise 404 queries are performed with no reason
# TODO: in builds view, don't show the success rate column if not relevant
# TODO: consider removing "@" from test names in scheduler implementation.
# TODO: add a full log link in test view.
# TODO: in index, refresh nightly builds.
# TODO: in index, add spinner for in-progress builds.
# TODO: circleci private repository.
# TODO: validate configuration after loading from yaml file
# TODO: when rebuilding a timer build, the causes contains both timer and the user who triggered the rebuild.
# TODO: browsing to an in progress build should show the link to view the build log.
# TODO: builds list pagination.
# TODO: unit tests start time format.
# TODO: cache menu items.


class _Object(dict):

    def __init__(self, data):
        self.update(data)


class Job(_Object):

    def __init__(self, data):
        super(Job, self).__init__(data)


class Build(_Object):

    def __init__(self, data):
        super(Build, self).__init__(data)

    @property
    def started_by(self):
        actions = self.get('actions', [])
        for action in actions:
            causes = action.get('causes', [])
            for cause in causes:
                description = cause['shortDescription']
                if 'Started by timer' in description:
                    return TIMER_USER
                if 'Started by build flow' in description:
                    return BUILD_FLOW
                elif 'Started by an SCM change' in description:
                    return SCM_CHANGE
                elif 'Started by' in description:
                    return cause.get('userName', 'Unknown')
        return 'Unknown'

    @property
    def is_timer_build(self):
        return self.started_by in (TIMER_USER, SCM_CHANGE, BUILD_FLOW)

    @property
    def duration_str(self):
        d = self.get('duration', 0)
        if d == 0:
            duration = timezone.make_aware(
                    datetime.datetime.now()) - self.started_at
        else:
            duration = datetime.timedelta(milliseconds=self.get('duration'))
        return str(duration).split('.')[0]

    @property
    def started_at(self):
        return timezone.make_aware(
                datetime.datetime.fromtimestamp(
                        int(self['timestamp']) / 1000),
                timezone.get_current_timezone())

    @property
    def passed(self):
        return self['result'] in PASSED_STRINGS

    @property
    def failed(self):
        return self['result'] in FAILED_STRINGS


class Case(_Object):
    def __init__(self, data, id):
        super(Case, self).__init__(data)
        self._id = id

    @property
    def id(self):
        return self._id

    @property
    def passed(self):
        return self['status'] in PASSED_STRINGS

    @property
    def failed(self):
        return self['status'] in FAILED_STRINGS

    @property
    def skipped(self):
        return self['status'] == SKIPPED_STRING

    @property
    def duration_str(self):
        return str(self.duration).split('.')[0]

    @property
    def duration(self):
        return datetime.timedelta(seconds=self.get('duration'))

    @property
    def short_class_name(self):
        return self['className'].split('.')[-1]


class Suite(_Object):
    def __init__(self, data):
        super(Suite, self).__init__(data)
        filtered_cases = self._filter_duplicate_cases(self.get('cases', []))
        self['cases'] = [
            Case(x, i) for i, x in enumerate(filtered_cases)]
        # TODO: cases matching should be done based on test name

    @property
    def passed_count(self):
        return len([x for x in self['cases'] if x['status'] in PASSED_STRINGS])

    @property
    def failed_count(self):
        return len([x for x in self['cases'] if x['status'] in FAILED_STRINGS])

    @property
    def skipped_count(self):
        return len([x for x in self['cases'] if x['status'] == SKIPPED_STRING])

    @property
    def total_count(self):
        return len(self['cases'])

    @property
    def total_duration(self):
        total = None
        for c in self['cases']:
            if total is None:
                total = c.duration
            else:
                total += c.duration
        return total

    @property
    def total_duration_str(self):
        return str(self.total_duration).split('.')[0]

    @staticmethod
    def _filter_duplicate_cases(cases):
        """This may occur when a test fails in test code or setup/teardown etc.
        Duplicates cause a confusion so its better to filter and have only
        one record per test, even if a failure will be missing."""
        tests = set()
        no_dups = []
        for case in cases:
            test_name = '{}.{}'.format(case['className'], case['name'])
            if test_name not in tests:
                no_dups.append(case)
                tests.add(test_name)
        return no_dups


class Report(_Object):
    def __init__(self, data):
        super(Report, self).__init__(data)
        self['suites'] = [Suite(x) for x in self.get('suites', [])]

    @property
    def passed_count(self):
        return self['passCount']

    @property
    def failed_count(self):
        return self['failCount']

    @property
    def skipped_count(self):
        return self['skipCount']

    @property
    def total_count(self):
        return self.passed_count + self.failed_count + self.skipped_count

    @property
    def passed_percentage(self):
        return math.trunc(
                round((self.passed_count / float(self.total_count)) * 100))

    @property
    def failed_percentage(self):
        return math.trunc(
                round((self.failed_count / float(self.total_count)) * 100))


class JenkinsResourceNotFound(IOError):

    def __init__(self, *args, **kwargs):
        super(JenkinsResourceNotFound, self).__init__(*args, **kwargs)


class Client(object):

    def __init__(self, base_url, username=None, password=None):
        self._base_url = base_url
        self._username = username
        self._password = password
        self._logger = logging.getLogger('django')

    def _query(self, job_name, tree=None, timeout=10):
        resource = '{}{}/api/json{}'.format(
            self._base_url[:-1] if self._base_url.endswith('/') else self._base_url,
            job_name,
            '?tree={}'.format(tree) if tree else '')

        self._logger.info('Jenkins query URL: {} [resource={}, tree={}]'.format(resource, job_name, tree))
        r = requests.get(resource,
                         auth=(self._username, self._password),
                         timeout=timeout)
        if r.status_code == 404:
            self._logger.warning('Resource not found: {}'.format(resource))
            raise JenkinsResourceNotFound(
                    'Jenkins resource not found: {}'.format(resource))
        if r.status_code != 200:
            raise RuntimeError('Error on request for: {} [status_code={}]'.format(resource, r.status_code))
        self._logger.info('Response content length: {}'.format(len(r.content)))
        result_json = r.json()
        self._logger.debug('Response for "{}":{}{}'.format(
                resource,
                os.linesep,
                json.dumps(result_json, indent=2)))
        return result_json

    @cache.cache_result(result_class=Job, expire=5*60)
    def get_job(self, job_name='', tree=None):
        """Get job. Since jobs has a builds field and these may change
        frequently, job responses are cached for 5 minutes."""
        if job_name:
            job_name = '/job/{}'.format('/job/'.join(job_name.split('/')))
        return self._query(job_name, tree=tree)

    @cache.cache_result(result_class=Build, cache_if_building=False)
    def get_build(self, job_name, build_number, tree=None):
        """Get build. Only completed builds are cached as in-progress builds
        whould always be retrieved from jenkins in order to monitor their
        state."""
        resource_name = '/job/{}/{}'.format(
                '/job/'.join(job_name.split('/')), build_number)
        return self._query(resource_name, tree=tree)

    @cache.cache_result(result_class=Report)
    def get_tests_report(self, job_name, build_number, tree=None):
        """Get test report. Since memcached's default max object size is 1mb
        we use compression and cache only less than 1mb compressed reports."""
        resource_name = '/job/{}/{}/testReport'.format(
                '/job/'.join(job_name.split('/')), build_number)
        return self._query(resource_name, tree=tree)

    def get_builds(self, job_name, last_build_number, size=25, tree=None):
        builds = [self.get_build(job_name, build_number, tree=tree)
                  for build_number in
                  range(max(last_build_number - size, 1), last_build_number + 1)]
        builds.reverse()
        return builds

    def get_full_build_log_url(self, job_name, build_number):
        resource_name = '{}/job/{}/{}/consoleFull'.format(
                self._base_url[:-1] if self._base_url.endswith('/') else self._base_url,
                '/job/'.join(job_name.split('/')),
                build_number)
        return resource_name


client = Client(config['jenkins']['url'],
                config['jenkins']['username'],
                config['jenkins']['password'])
