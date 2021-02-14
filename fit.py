import sys
import re
import time
import math
import argparse
import pickle
from functools import partial
from multiprocessing import Pool, cpu_count

import numpy as np
# np.seterr(all='raise')
import h5py

import wf_func as wff

global_start = time.time()
cpu_global_start = time.process_time()

psr = argparse.ArgumentParser()
psr.add_argument('-o', dest='opt', type=str, help='output file')
psr.add_argument('ipt', type=str, help='input file')
psr.add_argument('--met', type=str, help='fitting method')
psr.add_argument('--ref', type=str, nargs='+', help='reference file')
psr.add_argument('-N', '--Ncpu', dest='Ncpu', type=int, default=50)
args = psr.parse_args()

fipt = args.ipt
fopt = args.opt
reference = args.ref
method = args.met

gmu = 160.
gsigma = 40.
Thres = 0.2

def fitting(a, b):
    with h5py.File(fipt, 'r', libver='latest', swmr=True) as ipt:
        ent = ipt['Readout/Waveform'][:]
        dt = np.zeros((b - a) * window, dtype=opdt)
        start = 0
        end = 0
        for i in range(a, b):
            wave = ent[i]['Waveform'].astype(np.float64) * spe_pre[ent[i]['ChannelID']]['epulse']

            if method == 'xiaopeip':
#                 pet, cha, ped = wff.xiaopeip(wave, spe_pre[ent[i]['ChannelID']])
#                 wave = wave - ped
                pet, cha = wff.xiaopeip(wave, spe_pre[ent[i]['ChannelID']])
            elif method == 'lucyddm':
                pet, cha = wff.lucyddm(wave, spe_pre[ent[i]['ChannelID']])
            elif method == 'threshold':
                pet, cha = wff.threshold(wave, spe_pre[ent[i]['ChannelID']])
            elif method == 'fftrans':
                pet, cha = wff.waveformfft(wave, spe_pre[ent[i]['ChannelID']])
            elif method == 'findpeak':
                pet, cha = wff.findpeak(wave, spe_pre[ent[i]['ChannelID']])
            pet, cha = wff.clip(pet, cha, Thres)

            end = start + len(cha)
            dt['HitPosInWindow'][start:end] = pet
            cha = cha / cha.sum() * np.clip(np.abs(wave.sum()), 1e-6, np.inf)
            dt['Charge'][start:end] = cha
            dt['TriggerNo'][start:end] = ent[i]['TriggerNo']
            dt['ChannelID'][start:end] = ent[i]['ChannelID']
            start = end
    dt = dt[:end]
    dt = np.sort(dt, kind='stable', order=['TriggerNo', 'ChannelID'])
    return dt

spe_pre = wff.read_model(reference[0])
opdt = np.dtype([('TriggerNo', np.uint32), ('ChannelID', np.uint32), ('HitPosInWindow', np.float64), ('Charge', np.float64)])
with h5py.File(fipt, 'r', libver='latest', swmr=True) as ipt:
    l = len(ipt['Readout/Waveform'])
    print('{} waveforms will be computed'.format(l))
    window = len(ipt['Readout/Waveform'][0]['Waveform'])
    assert window >= len(spe_pre[0]['spe']), 'Single PE too long which is {}'.format(len(spe_pre[0]['spe']))
    Mu = ipt['Readout/Waveform'].attrs['mu']
    Tau = ipt['Readout/Waveform'].attrs['tau']
    Sigma = ipt['Readout/Waveform'].attrs['sigma']
if args.Ncpu == 1:
    slices = [[0, l]]
else:
    chunk = l // args.Ncpu + 1
    slices = np.vstack((np.arange(0, l, chunk), np.append(np.arange(chunk, l, chunk), l))).T.astype(int).tolist()
print('Initialization finished, real time {0:.02f}s, cpu time {1:.02f}s'.format(time.time() - global_start, time.process_time() - cpu_global_start))
tic = time.time()
cpu_tic = time.process_time()

with Pool(min(args.Ncpu, cpu_count())) as pool:
    select_result = pool.starmap(fitting, slices)
result = np.hstack(select_result)
result = np.sort(result, kind='stable', order=['TriggerNo', 'ChannelID'])
print('Prediction generated, real time {0:.02f}s, cpu time {1:.02f}s'.format(time.time() - tic, time.process_time() - cpu_tic))
with h5py.File(fopt, 'w') as opt:
    dset = opt.create_dataset('photoelectron', data=result, compression='gzip')
    dset.attrs['Method'] = method
    dset.attrs['mu'] = Mu
    dset.attrs['tau'] = Tau
    dset.attrs['sigma'] = Sigma
    print('The output file path is {}'.format(fopt))
print('Finished! Consuming {0:.02f}s in total, cpu time {1:.02f}s.'.format(time.time() - global_start, time.process_time() - cpu_global_start))