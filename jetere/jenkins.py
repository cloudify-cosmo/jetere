
import datetime
import json
import logging
import math
import os

import requests

from django.utils import timezone

PASSED_STRINGS = ('PASSED', 'FIXED', 'SUCCESS')
FAILED_STRINGS = ('FAILED', 'REGRESSION', 'FAILURE')
SKIPPED_STRING = 'SKIPPED'

TIMER_USER = 'Timer'

# TODO: handle jenkins 404
# TODO: Cache responses.
# TODO: Use tree (maybe not relevant if there's proper caching)
# TODO: merge tests with the same name (also has an effect on duration calculation) see system-tests #733
# TODO: consider removing "@" from test names in scheduler implementation.


class _Object(dict):

    def __init__(self, data):
        self.update(data)


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
                elif 'Started by' in description:
                    return cause.get('userName', 'Unknown')
        return 'Unknown'

    @property
    def duration_str(self):
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


class Suite(_Object):
    def __init__(self, data):
        super(Suite, self).__init__(data)
        self['cases'] = [
            Case(x, i) for i, x in enumerate(self.get('cases', []))]

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


class Report(_Object):
    def __init__(self, data):
        super(Report, self).__init__(data)
        self['suites'] = [Suite(x) for x in self.get('suites', [])]

    @property
    def passed_count(self):
        return sum(x.passed_count for x in self['suites'])

    @property
    def failed_count(self):
        return sum(x.failed_count for x in self['suites'])

    @property
    def skipped_count(self):
        return sum(x.skipped_count for x in self['suites'])

    @property
    def total_count(self):
        return sum(x.total_count for x in self['suites'])

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
        self._logger.info('Jenkins query resource: {} [jenkins_resource={}, tree={}]'.format(resource, job_name, tree))
        r = requests.get(resource,
                         auth=(self._username, self._password),
                         timeout=timeout)
        if r.status_code == 404:
            self._logger.warning('Resource not found: {}'.format(resource))
            raise JenkinsResourceNotFound(
                    'Jenkins resource not found: {}'.format(resource))
        if r.status_code != 200:
            raise RuntimeError('Error on request for: {} [status_code={}]'.format(resource, r.status_code))
        result_json = r.json()
        self._logger.info('Response for "{}":{}{}'.format(resource,
                                                          os.linesep,
                                                          json.dumps(result_json, indent=2)))
        return result_json

    def get_job(self, job_name='', tree=None):
        if job_name:
            job_name = '/job/{}'.format('/job/'.join(job_name.split('/')))
        return self._query(job_name, tree=tree)

    def get_builds(self, job_name, last_build_number, size=25, tree=None):
        builds = [self.get_build(job_name, build_number, tree=tree)
                  for build_number in
                  range(max(last_build_number - size, 1), last_build_number + 1)]
        builds.reverse()
        return builds

    def get_build(self, job_name, build_number, tree=None):
        resource_name = '/job/{}/{}'.format(
                '/job/'.join(job_name.split('/')), build_number)
        return Build(self._query(resource_name, tree=tree))

    def get_tests_report(self, job_name, build_number, tree=None):
        resource_name = '/job/{}/{}/testReport'.format(
                '/job/'.join(job_name.split('/')), build_number)
        return Report(self._query(resource_name, tree=tree))

    def get_full_build_log_url(self, job_name, build_number):
        resource_name = '{}/job/{}/{}/consoleFull'.format(
                self._base_url[:-1] if self._base_url.endswith('/') else self._base_url,
                '/job/'.join(job_name.split('/')),
                build_number)
        return resource_name
