
from functools import wraps

from django.shortcuts import render

from . import models


def _get_jobs():
    return models.Job.objects.all().order_by('name')


def _get_default_template_vars():
    return {
        'last_update': models.Sync.objects.all()[0].last_update,
        'jobs': _get_jobs()
    }


def render_me(html_file):

    def decorator(view_func):

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            view_vars = view_func(request, *args, **kwargs)
            template_vars = _get_default_template_vars().copy()
            template_vars.update(view_vars)
            return render(request, html_file, template_vars)

        return _wrapped_view

    return decorator


@render_me('main.html')
def index(request):
    return {}


@render_me('builds.html')
def builds(request, job_id, timer=False, filter='All'):
    job = models.Job.objects.all().get(id=job_id)
    if timer:
        builds = models.Build.objects.all().filter(
            job_id=job_id, started_by='Timer').order_by('-number')
    else:
        builds = models.Build.objects.all().filter(
            job_id=job_id).order_by('-number')
    return {
        'current_job': job,
        'builds': builds,
        'filter': filter
    }


@render_me('tests.html')
def tests(request, build_id, failed=False, filter='All'):
    build = models.Build.objects.get(id=build_id)
    build_tests = models.Test.objects.all().filter(build_id=build_id)
    suites = {}
    tests_summary = {'passed': 0, 'failed': 0, 'total': 0}
    for t in build_tests:
        suite_name = t.name.split('@')[1].strip() if '@' in t.name else t.name
        if suite_name not in suites:
            suites[suite_name] = {
                'tests': [],
                'passed': 0,
                'total': 0,
            }
        suite = suites[suite_name]

        suite['tests'].append(t)
        if t.passed:
            suite['passed'] += 1
            tests_summary['passed'] += 1
        suite['total'] += 1
        tests_summary['total'] += 1
        tests_summary['failed'] = tests_summary['total'] - tests_summary['passed']
    if failed:
        for suite_name in suites.keys():
            suite_info = suites[suite_name]
            suite_info['tests'] = [x for x in suite_info['tests'] if x.failed or x.skipped]
            if not suite_info['tests']:
                del suites[suite_name]

    return {
        'current_job': build.job,
        'current_build': build,
        'suites': suites,
        'tests_summary': tests_summary,
        'filter': filter
    }


def failed_tests(request, build_id):
    return tests(request, build_id, failed=True, filter='Failed & Skipped')


def timer_builds(request, job_id):
    return builds(request, job_id, timer=True, filter='Timer')


@render_me(html_file='logs.html')
def logs(request, test_id):
    test_logs = models.TestLogs.objects.get(test_id=test_id)
    return {
        'current_job': test_logs.test.build.job,
        'current_build': test_logs.test.build,
        'current_test': test_logs.test,
        'test_logs': test_logs
    }
