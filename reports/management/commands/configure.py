import json
import os

from django.core.management.base import BaseCommand

from jetere import jenkins

CONFIG_DIR_PATH = os.path.expanduser('~/.jetere')
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR_PATH, 'config.json')


def load_jenkins_configuration_from_file():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)


class Command(BaseCommand):
    help = 'Configure Jenkins'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--jenkins-url',
                            required=True,
                            type=str,
                            help='Jenkins URL')
        parser.add_argument('--jenkins-username',
                            required=True,
                            type=str,
                            help='Jenkins username')
        parser.add_argument('--jenkins-password',
                            required=True,
                            type=str,
                            help='Jenkins username')

    def handle(self, *args, **options):
        config = {
            'jenkins_url': options['jenkins_url'],
            'jenkins_username': options['jenkins_username'],
            'jenkins_password': options['jenkins_password'],
        }

        if not os.path.exists(CONFIG_DIR_PATH):
            os.makedirs(CONFIG_DIR_PATH)

        self.stdout.write('Writing configuration to %s' % CONFIG_FILE_PATH)

        with open(CONFIG_FILE_PATH, 'w') as f:
            f.write(json.dumps(config, indent=2))

        self.stdout.write('Verifying jenkins connectivity...')
        client = jenkins.Client(config['jenkins_url'],
                                config['jenkins_username'],
                                config['jenkins_password'])
        try:
            client.get_job()
            self.stdout.write(
                    self.style.SUCCESS('Successfully connected to jenkins '
                                       'server. done!'))
        except Exception as e:
            self.stdout.write(
                    self.style.ERROR(
                            'Unable to connect to jenkins server at: '
                            '{}{}{}'.format(config['jenkins_url'],
                                            os.linesep,
                                            str(e))))
