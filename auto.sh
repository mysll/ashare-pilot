#!/bin/bash
export PYTHONIOENCODING=utf-8
env -u VIRTUAL_ENV uv run --frozen ashare-pilot automation scheduler run "$@"
