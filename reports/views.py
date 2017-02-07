import logging
import re
from functools import wraps

import urllib2

from django import http
from django.shortcuts import render
from django.views.defaults import page_not_found

from . import models
from . import jenkins
from .jenkins import client as jenkins_client
from .config import instance as config

logger = logging.getLogger('django')

job_definitions = config['jenkins']['job_definitions']

DEFAULT_MAX_BUILDS = 20
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


def get_last_timer_builds(full_job_name, last_build_number):
    timer_builds = []
    counter = 0
    while len(timer_builds) < 5:
        last_build_number -= 1
        if last_build_number == 0:
            break
        counter += 1
        b = jenkins_client.get_build(full_job_name, last_build_number)
        if b and b.is_timer_build:
            timer_builds.append(b)
        if counter == 100:
            raise RuntimeError(
                    'get_last_timer_builds exceeded 100 build retrievals!')
    return timer_builds


def generate_tests_history(report, nightly_builds):
    tests = {}

    def _collect_tests_from_suite(suite, build_number):
        for case in suite.get('cases', []):
            test_name = '{}.{}.{}'.format(suite['name'], case['className'], case['name'])
            if test_name not in tests:
                tests[test_name] = []
            tests[test_name].append({
                'build_number': build_number,
                'case': case
            })

    for b in nightly_builds:
        if b.report:
            for s in b.report.get('suites', []):
                _collect_tests_from_suite(s, b['number'])

    for s in report.get('suites', []):
        for c in s.get('cases', []):
            test_name = '{}.{}.{}'.format(s['name'], c['className'], c['name'])
            setattr(c, 'history', tests.get(test_name))


@render_me('build.html')
def build(request, job_name, build_number):
    build_number = int(build_number)
    job_def = find_job_definition(job_name)
    if not job_def:
        return page_not_found(
                request, ValueError('Unknown job: {}'.format(job_name)))
    full_job_name = '{}/{}'.format(job_def['name'], job_name)
    report_tree = 'passCount,failCount,skipCount,suites[name,cases[name,className,status,duration]]'  # NOQA
    try:
        logger.info('Getting test report for {}/{}'.format(
                full_job_name, build_number))
        report = jenkins_client.get_tests_report(full_job_name,
                                                 build_number,
                                                 tree=report_tree)
        logger.info('Getting last timer builds for {}/{}'.format(
                full_job_name, build_number))
        nightly_builds = get_last_timer_builds(full_job_name, build_number)
        for b in nightly_builds:
            logger.info('Getting test report for timer build {}/{}'.format(
                    full_job_name, b['number']))
            try:
                r = jenkins_client.get_tests_report(full_job_name,
                                                    b['number'],
                                                    tree=report_tree)
                setattr(b, 'report', r)
            except jenkins.JenkinsResourceNotFound:
                setattr(b, 'report', None)
        logger.info('Generating tests history for test report {}/{}'.format(
                full_job_name, build_number))
        generate_tests_history(report, nightly_builds)
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


def get_manager_logs_for_test(build_number, case):
    url = 'http://cloudify-tests-logs.s3.amazonaws.com/{build_number}/{build_number}-{class_name}-{test_name}/links.html'.format(
        build_number=build_number,
        class_name=case.short_class_name,
        test_name=case['name'])
    try:
        response = urllib2.urlopen(url)
    except urllib2.HTTPError as e:
        return None
    else:
        return response.read()


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
        'case': case,
        'full_build_log_url': jenkins_client.get_full_build_log_url(
                full_job_name, build_number),
        'manager_logs': get_manager_logs_for_test(build_number, case)
    }
