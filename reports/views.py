import logging
import re
from functools import wraps

from django import http
from django.shortcuts import render
from django.views.defaults import page_not_found

from . import models
from . import jenkins
from .jenkins import client as jenkins_client
from .config import instance as config

logger = logging.getLogger('django')

job_definitions = config['jenkins']['job_definitions']

DEFAULT_MAX_BUILDS = 10
NIGHTLY_BUILD_SEARCH_LIMIT = 10


def _get_jobs():
    return models.Job.objects.all().order_by('name')


def _get_default_template_vars():
    # TODO: auto inject view argument as template args
    jobs_list = []
    for x in job_definitions:
        job = jenkins_client.get_job(x['name'])
        nested_jobs = [a['name'] for a in list_nested_jobs(job, x['regex'])]
        jobs = [jenkins_client.get_job('{}/{}'.format(job['name'], a)) for a in nested_jobs]
        jobs_list.extend(jobs)
    return {
            'jobs_list': jobs_list
        }


def render_me(html_file, inject_default_template_vars=False):

    def decorator(view_func):

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            template_vars = _get_default_template_vars().copy()
            if inject_default_template_vars:
                kwargs.update(template_vars)
            view_vars = view_func(request, *args, **kwargs) or {}
            if isinstance(view_vars, http.HttpResponse):
                return view_vars
            template_vars.update(view_vars)
            return render(request, html_file, template_vars)

        return _wrapped_view

    return decorator


def list_nested_jobs(job, regex):
    return [x for x in job['jobs'] if re.match(regex, x['name'])]


def find_job_definition(job_name):
    for job_def in job_definitions:
        if re.match(job_def['regex'], job_name):
            return job_def
    return None


def find_nightly_build(job):
    """The function will query jenkins and find the first job
    started by timer and fetch its report."""
    job_name = job['name']
    job_def = find_job_definition(job_name)
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    build_numbers = [x['number'] for x in job['builds']]
    for build_number in build_numbers[:NIGHTLY_BUILD_SEARCH_LIMIT]:
        b = jenkins_client.get_build(full_job_name, build_number)
        if b.started_by in (jenkins.TIMER_USER, jenkins.SCM_CHANGE):
            try:
                b['report'] = jenkins_client.get_tests_report(full_job_name,
                                                              build_number)
            except jenkins.JenkinsResourceNotFound:
                pass
            return b
    return None


@render_me('main.html', inject_default_template_vars=True)
def index(request, jobs_list, **_):
    for j in jobs_list:
        nightly_build = find_nightly_build(j)
        if nightly_build:
            j['nightly_build'] = nightly_build


@render_me('job.html')
def job(request, job_name):
    job_def = find_job_definition(job_name)
    if not job_def:
        return page_not_found(
                request, ValueError('Unknown job: {}'.format(job_name)))
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    job = jenkins_client.get_job(full_job_name)
    last_build_number = job['lastBuild']['number']
    builds = jenkins_client.get_builds(full_job_name,
                                         last_build_number,
                                         size=DEFAULT_MAX_BUILDS)
    return {
        'job': job,
        'job_name': job_name,
        'builds': builds
    }


@render_me('build.html')
def build(request, job_name, build_number):
    job_def = find_job_definition(job_name)
    if not job_def:
        return page_not_found(
                request, ValueError('Unknown job: {}'.format(job_name)))
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    try:
        report = jenkins_client.get_tests_report(full_job_name, build_number)
    except jenkins.JenkinsResourceNotFound:
        report = None
    return {
        'job_name': job_name,
        'build_number': build_number,
        'report': report,
        'full_build_log_url': jenkins_client.get_full_build_log_url(
                full_job_name, build_number)
    }


def find_suite(report, suite_name):
    for suite in report['suites']:
        if suite['name'] == suite_name:
            return suite
    return None


@render_me('test.html')
def test(request, job_name, build_number, suite_name, case_index):
    job_def = find_job_definition(job_name)
    if not job_def:
        return page_not_found(
                request, ValueError('Unknown job: {}'.format(job_name)))
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    report = jenkins_client.get_tests_report(full_job_name, build_number)
    suite = find_suite(report, suite_name)
    if not suite:
        return page_not_found(
            request, ValueError('Suite not found: "{}"'.format(suite_name)))
    case = suite['cases'][int(case_index)]
    return {
        'job_name': job_name,
        'build_number': build_number,
        'suite_name': suite_name,
        'case': case
    }
