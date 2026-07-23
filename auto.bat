@echo off
set "VIRTUAL_ENV="
uv run --frozen ashare-pilot automation scheduler run
