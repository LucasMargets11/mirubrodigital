#!/usr/bin/env python
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / 'src'
if str(SRC_DIR) not in sys.path:
  sys.path.append(str(SRC_DIR))


def main() -> None:
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
  from django.core.management import execute_from_command_line

  execute_from_command_line(sys.argv)


if __name__ == '__main__':
  main()
