
import datetime
import logging

import requests

from reports import cache

CIRCLE_BUILD_URL = 'https://circleci.com/api/v1.1/project/github/{project}/tree/{branch}'  # NOQA


PASSED_STRINGS = ['success', 'fixed']
FAILED_STRINGS = ['failed']


class Build(dict):

    def __init__(self, data):
        self.update(data)

    @property
    def passed(self):
        return self['status'] in PASSED_STRINGS

    @property
    def duration_str(self):
        duration = datetime.timedelta(
                milliseconds=self.get('build_time_millis'))
        return str(duration).split('.')[0]


class CircleCIClient(object):

    def __init__(self):
        super(CircleCIClient, self).__init__()
        self._logger = logging.getLogger('django')

    def get_build(self, project, branch='master'):
        url = CIRCLE_BUILD_URL.format(project=project, branch=branch)
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return [Build(x) for x in r.json()]
        raise requests.HTTPError(
                'HTTP request error [url={}, status_code={}]'.format(
                        url, r.status_code))

    @cache.cache_result(Build, key='circleci', expire=60*5)
    def get_builds(self, projects, branch='master'):
        result = []
        for project in projects:
            try:
                builds = self.get_build(project, branch=branch)
                if len(builds) > 0:
                    result.append(builds[0])
            except Exception as e:
                # TODO: errors should be added to the list with a failure entry.
                self._logger.error('Error getting circleci build for project '
                                   '"{}": {}'.format(project, str(e)))
        return result
