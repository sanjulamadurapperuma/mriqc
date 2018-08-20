#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
""" Helper functions """
from __future__ import print_function, division, absolute_import, unicode_literals

from pathlib import Path
from os import path as op
from glob import glob

import collections
import json
import pandas as pd

IMTYPES = {
    'T1w': 'anat',
    'T2w': 'anat',
    'bold': 'func',
}

BIDS_COMP = collections.OrderedDict([
    ('subject_id', 'sub'), ('session_id', 'ses'), ('task_id', 'task'),
    ('acq_id', 'acq'), ('rec_id', 'rec'), ('run_id', 'run')
])

BIDS_EXPR = """\
^sub-(?P<subject_id>[a-zA-Z0-9]+)(_ses-(?P<session_id>[a-zA-Z0-9]+))?\
(_task-(?P<task_id>[a-zA-Z0-9]+))?(_acq-(?P<acq_id>[a-zA-Z0-9]+))?\
(_rec-(?P<rec_id>[a-zA-Z0-9]+))?(_run-(?P<run_id>[a-zA-Z0-9]+))?\
"""


def split_ext(in_file, out_file=None):
    import os.path as op
    if out_file is None:
        fname, ext = op.splitext(op.basename(in_file))
        if ext == '.gz':
            fname, ext2 = op.splitext(fname)
            ext = ext2 + ext
        return fname, ext
    else:
        return split_ext(out_file)


def reorder_csv(csv_file, out_file=None):
    """
    Put subject, session and scan in front of csv file

    :param str csv_file: the input csv file
    :param str out_file: if provided, a new csv file is created

    :return: the path to the file with the columns reordered


    """
    if isinstance(csv_file, list):
        csv_file = csv_file[-1]

    if out_file is None:
        out_file = csv_file

    dataframe = pd.read_csv(csv_file)
    cols = dataframe.columns.tolist()  # pylint: disable=no-member
    try:
        cols.remove('Unnamed: 0')
    except ValueError:
        # The column does not exist
        pass

    for col in ['scan', 'session', 'subject']:
        cols.remove(col)
        cols.insert(0, col)

    dataframe[cols].to_csv(out_file)
    return out_file


def rotate_files(fname):
    """A function to rotate file names"""
    import glob
    import os
    import os.path as op

    name, ext = op.splitext(fname)
    if ext == '.gz':
        name, ext2 = op.splitext(fname)
        ext = ext2 + ext

    if not op.isfile(fname):
        return

    prev = glob.glob('{}.*{}'.format(name, ext))
    prev.insert(0, fname)
    prev.append('{0}.{1:d}{2}'.format(name, len(prev) - 1, ext))
    for i in reversed(list(range(1, len(prev)))):
        os.rename(prev[i - 1], prev[i])


def bids_path(subid, sesid=None, runid=None, prefix=None, out_path=None, ext='json'):
    import os.path as op
    fname = '{}'.format(subid)
    if prefix is not None:
        if not prefix.endswith('_'):
            prefix += '_'
        fname = prefix + fname
    if sesid is not None:
        fname += '_ses-{}'.format(sesid)
    if runid is not None:
        fname += '_run-{}'.format(runid)

    if out_path is not None:
        fname = op.join(out_path, fname)
    return op.abspath(fname + '.' + ext)


def generate_pred(derivatives_dir, output_dir, mod):
    """
    Reads the metadata in the JIQM (json iqm) files and
    generates a corresponding prediction CSV table
    """

    if mod != 'T1w':
        return None

    # If some were found, generate the CSV file and group report
    out_csv = op.join(output_dir, mod + '_predicted_qa.csv')
    jsonfiles = glob(op.join(derivatives_dir, 'sub-*_%s.json' % mod))
    if not jsonfiles:
        return None

    headers = list(BIDS_COMP.keys()) + ['mriqc_pred']
    predictions = {k: [] for k in headers}

    for jsonfile in jsonfiles:
        with open(jsonfile, 'r') as jsondata:
            data = json.load(jsondata).pop('bids_meta', None)

        if data is None:
            continue

        for k in headers:
            predictions[k].append(data.pop(k, None))

    dataframe = pd.DataFrame(
        predictions).sort_values(by=list(BIDS_COMP.keys()))

    # Drop empty columns
    dataframe.dropna(axis='columns', how='all', inplace=True)

    bdits_cols = list(set(BIDS_COMP.keys()) & set(dataframe.columns.ravel()))

    # Drop duplicates
    dataframe.drop_duplicates(bdits_cols,
                              keep='last', inplace=True)

    dataframe[bdits_cols + ['mriqc_pred']].to_csv(out_csv, index=False)
    return out_csv


def generate_tsv(output_dir, mod):
    """
    Generates a tsv file from all json files in the derivatives directory
    """

    # If some were found, generate the CSV file and group report
    out_tsv = output_dir / ('group_%s.tsv' % mod)
    jsonfiles = list(output_dir.glob('sub-*/**/%s/sub-*_%s.json' % (IMTYPES[mod], mod)))
    if not jsonfiles:
        return None, out_tsv

    datalist = []
    for jsonfile in jsonfiles:
        dfentry = _read_and_save(jsonfile)

        if dfentry is not None:
            bids_name = str(Path(jsonfile.name).stem)
            dfentry.pop('bids_meta', None)
            dfentry.pop('provenance', None)
            dfentry['bids_name'] = bids_name
            datalist.append(dfentry)

    dataframe = pd.DataFrame(datalist)
    cols = dataframe.columns.tolist()  # pylint: disable=no-member
    dataframe = dataframe.sort_values(by=['bids_name'])

    # Drop duplicates
    dataframe.drop_duplicates(['bids_name'], keep='last', inplace=True)

    # Set filename at front
    cols.insert(0, cols.pop(cols.index('bids_name')))
    dataframe[cols].to_csv(str(out_tsv), index=False, sep='\t')
    return dataframe, out_tsv


def _read_and_save(in_file):
    with open(in_file, 'r') as jsondata:
        data = json.load(jsondata)
    return data if data else None


def _flatten(in_dict, parent_key='', sep='_'):
    items = []
    for k, val in list(in_dict.items()):
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(val, collections.MutableMapping):
            items.extend(list(_flatten(val, new_key, sep=sep).items()))
        else:
            items.append((new_key, val))
    return dict(items)


def _flatten_dict(indict):
    out_qc = {}
    for k, value in list(indict.items()):
        if not isinstance(value, dict):
            out_qc[k] = value
        else:
            for subk, subval in list(value.items()):
                if not isinstance(subval, dict):
                    out_qc['_'.join([k, subk])] = subval
                else:
                    for ssubk, ssubval in list(subval.items()):
                        out_qc['_'.join([k, subk, ssubk])] = ssubval
    return out_qc
