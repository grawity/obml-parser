#!/usr/bin/env python3
# Converter of Opera Mini OBML saved pages into HTML
#
# (c) 2014–2022 Mantas Mikulėnas <grawity@gmail.com>
# Released under the MIT License
#
# Originally intended to extract original URLs from saved pages, after Opera
# dropped binary compatibilty between minor releases and left me with a bunch
# of unreadable saved pages in v15.

import argparse
import glob
import sys

from lib.process import process_one_file

parser = argparse.ArgumentParser()
parser.add_argument("obml_file", nargs="*")
args = parser.parse_args()

if not args.obml_file:
    args.obml_file = glob.glob("*.obml*")

for arg in args.obml_file:
    process_one_file(arg)
