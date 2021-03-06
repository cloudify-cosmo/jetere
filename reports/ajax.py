import logging

from django.shortcuts import render

from reports import jenkins
from reports.circleci import CircleCIClient
from reports.config import instance as config
from views import DEFAULT_MAX_BUILDS
from views import find_job_definition
from .jenkins import client as jenkins_client


logger = logging.getLogger('django')


circleci_projects = config['circleci']['projects']


def unit_tests(request, **_):
    circleci = CircleCIClient()
    circleci_builds = circleci.get_builds(circleci_projects)
    circleci_builds.sort(key=lambda x: x['status'])
    return render(request, 'ajax/unit-tests.html', {
        'cci_builds': circleci_builds})


def job_builds(request, job_name, **_):
    job_def = find_job_definition(job_name)
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    job = jenkins_client.get_job(full_job_name, tree='name,lastBuild[number]')
    last_build_number = job['lastBuild']['number']
    builds = jenkins_client.get_builds(full_job_name,
                                       last_build_number,
                                       size=DEFAULT_MAX_BUILDS)
    for build in builds:
        try:
            build['report'] = jenkins_client.get_tests_report(
                    full_job_name,
                    build['number'],
                    tree='passCount,failCount,skipCount')
        except jenkins.JenkinsResourceNotFound:
            pass

    return render(request, 'ajax/job-builds.html', {
        'job': job,
        'job_name': job_name,
        'builds': builds
    })
