# -*- coding: utf-8 -*-

import h5py
import argparse

psr = argparse.ArgumentParser()
psr.add_argument('-o', dest='opt', help='outputDir')
psr.add_argument('--ref', dest='ref', help='truthFile')
psr.add_argument('ipt', help='input')
args = psr.parse_args()

import csv
import numpy as np
import scipy.stats


import itertools as it

def wpdistance(df_ans, df_sub):
    '''
    do the actual grade

    return the mean Wasserstain and Poisson distances.
    '''

    # number of channels is 30
    pmtNum = np.max(df_ans['ChannelID']) + 1
    e_ans = df_ans['EventID']*pmtNum + df_ans['ChannelID']
    e_ans, i_ans = np.unique(e_ans, return_index=True)
    gl = len(e_ans)
    opdt = np.dtype([('EventID', np.uint32), ('ChannelID', np.uint32), ('PEnum', np.uint16), ('wdist', np.float32), ('pdist', np.float32)])
    dt = np.zeros(gl, dtype=opdt)

    e_sub = df_sub['EventID']*pmtNum + df_sub['ChannelID']
    e_sub, i_sub = np.unique(e_sub, return_index=True)

    # bad: additional memory allocation
    i_sub = np.append(i_sub, len(df_sub))

    p = 0
    ejd = e_sub[p]
    # append an additional largest eid, so that the last event is also graded
    for eid, c, i0, i in zip(e_ans, range(gl), np.nditer(i_ans), it.chain(np.nditer(i_ans[1:]), [len(df_ans)])):
        while ejd < eid:
            p += 1
            ejd = e_sub[p]
        assert ejd == eid, 'Answer must include Event {} Channel {}.'.format(eid//pmtNum, eid % pmtNum)

        j0 = i_sub[p]; j = i_sub[p+1]

        # scores
        wl = df_sub[j0:j]['Weight']
        dt['wdist'][c] = scipy.stats.wasserstein_distance(df_ans[i0:i]['PETime'], df_sub[j0:j]['PETime'], v_weights=wl)
        Q = i-i0; q = np.sum(wl)
        dt['PEnum'][c] = Q
        dt['pdist'][c] = np.abs(Q - q) * scipy.stats.poisson.pmf(Q, Q)
        dt['EventID'][c] = eid//pmtNum
        dt['ChannelID'][c] = eid % pmtNum
        print('\rGrading Process:|{}>{}|{:6.2f}%'.format(((20 * c)//gl)*'-', (19-(20*c)//gl)*' ', 100 * ((c+1)/gl)), end = '' if c != gl-1 else '\n')

    return dt
if __name__ == '__main__':
    with h5py.File(args.ref, 'r', libver='latest', swmr=True) as ref, h5py.File(args.ipt, 'r', libver='latest', swmr=True) as ipt:
        df_ans = ref['GroundTruth'][...]
        df_sub = ipt['Answer'][...]
    dt = wpdistance(df_ans, df_sub)
    # wd = dt['wdist'].average()
    # pd = dt['pdist'].average()
    with h5py.File('{}/distanceDistribution.h5'.format(args.opt), 'w') as h5f:
        dset = h5f.create_dataset('Record', data=dt, compression='gzip')