#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from scilpy.io.deprecator import deprecate_script
from scripts.scil_tractogram_shuffle import main as new_main


DEPRECATION_MSG = """
This script has been renamed scil_tractogram_shuffle.py. Please change
your existing pipelines accordingly. We will try to keep the following
convention:

- Scripts on 'streamlines' treat each streamline individually.
- Scripts on 'tractograms' apply the same operation on all streamlines of the
  tractogram.
"""


@deprecate_script("scil_shuffle_streamlines.py", DEPRECATION_MSG, '1.7.0')
def main():
    new_main()


if __name__ == "__main__":
    main()