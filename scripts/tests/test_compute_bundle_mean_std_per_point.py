#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile

from scilpy.io.fetcher import get_testing_files_dict, fetch_data, get_home


# If they already exist, this only takes 5 seconds (check md5sum)
fetch_data(get_testing_files_dict(), keys=['tractometry.zip'])
tmp_dir = tempfile.TemporaryDirectory()


def test_help_option(script_runner):
    ret = script_runner.run('scil_compute_bundle_mean_std.py', '--help')
    assert ret.success


def test_execution_tractometry(script_runner):
    os.chdir(os.path.expanduser(tmp_dir.name))
    in_bundle = os.path.join(get_home(), 'tractometry',
                             'IFGWM.trk')
    in_label = os.path.join(get_home(), 'tractometry',
                            'label.npz')
    in_distance = os.path.join(get_home(), 'tractometry',
                               'distance.npz')
    in_ref = os.path.join(get_home(), 'tractometry',
                          'mni_masked.nii.gz')
    ret = script_runner.run('scil_compute_bundle_mean_std_per_point.py',
                            in_bundle, in_label, in_distance, in_ref,
                            '--density_weighting', '--distance_weighting',
                            '--out_json', 'metric_label.json')

    assert ret.success
