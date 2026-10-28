#!/bin/sh
export APP_LOG=/tmp/svc.out
export APP_LEVEL=INFO
exec python3 -m app
