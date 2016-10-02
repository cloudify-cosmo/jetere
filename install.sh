#!/bin/bash

pip install -r requirements.txt

./manage.py makemigrations

./manage.py migrate


