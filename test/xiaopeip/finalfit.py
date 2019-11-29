# -*- coding: utf-8 -*-

import numpy as np
from scipy import optimize as opti
import h5py
import time
# import standard
import matplotlib.pyplot as plt
from scipy.fftpack import fft, ifft
import argparse

psr = argparse.ArgumentParser()
psr.add_argument('-o', dest='opt', help='output')
psr.add_argument('ipt', help='input')
psr.add_argument('--ref')
args = psr.parse_args()

def norm_fit(x, M, p):
    return np.linalg.norm(p - np.matmul(M, x))

def main(fopt, fipt, aver_spe_path):
    speFile = h5py.File(aver_spe_path, 'r', libver='latest', swmr=True)
    spemean = np.array(speFile['spe'])
    aver = speFile['averzero']
    opdt = np.dtype([('EventID', np.uint32), ('ChannelID', np.uint8), ('PETime', np.uint16), ('Weight', np.float16)])

    with h5py.File(fipt, 'r', libver='latest', swmr=True) as ipt, h5py.File(fopt, 'w') as opt:
        ent = ipt['Waveform']
        l = len(ent)
        print('{} waveforms will be computed'.format(l))
        dt = np.zeros(l * 1029, dtype=opdt)
        start = 0
        end = 0
        start_t = time.time()
        for i in range(l):
            wf_input = ent[i]['Waveform']
            wave = wf_input - 972 - aver
            lowp = np.argwhere(wave < -6.5).flatten()
            flag = 1
            if len(lowp) != 0:
                if lowp[0] < 1:
                    lowp = lowp[1:]
                if lowp[-1] >= 1028:
                    lowp = lowp[:-1]
                if len(lowp) != 0:
                    panel = np.zeros(1029)
                    for j in lowp:
                        head = j-7 if j-7 > 0 else 0
                        tail = j+15+1 if j+15+1 <= 1029 else 1029
                        panel[head:tail] = 1
                    nihep = np.argwhere(panel == 1).flatten()
                    xuhao = np.argwhere(wave[lowp+1]-wave[lowp]-wave[lowp-1]+wave[lowp-2] > 1.5).flatten()
                    if len(xuhao) != 0:
                        possible = np.unique(np.concatenate((lowp[xuhao]-10,lowp[xuhao]-9,lowp[xuhao]-8)))
                        ans0 = np.zeros((len(possible), 1))
                        ans0 = np.zeros_like(possible).astype(np.float64)
                        b = np.zeros((len(possible), 2))
                        b[:, 1] = np.inf
                        mne = spemean[np.mod(nihep.reshape(len(nihep), 1) - possible.reshape(1, len(possible)), 1029)]
                        ans = opti.fmin_l_bfgs_b(norm_fit, ans0, args=(mne, wave[nihep]), approx_grad=True, bounds=b)
                        pf = ans[0]
                    else:
                        flag = 0
                else:
                    flag = 0
            else:
                flag = 0
            if flag == 0:
                t = np.where(wave == wave.min())[0][:1] - np.argmin(spemean)
                possible = t if t >= 0 else 0
                pf = np.array([1])
            pf[pf < 0.1] = 0
            lenpf = np.size(np.where(pf > 0))
            pet = possible[pf > 0]
            pwe = pf[pf > 0]
            pwe = pwe.astype(np.float16)
            end = start + lenpf
            dt['PETime'][start:end] = pet
            dt['Weight'][start:end] = pwe
            dt['EventID'][start:end] = ent[i]['EventID']
            dt['ChannelID'][start:end] = ent[i]['ChannelID']
            start = end
            print('\rAnsw Generating:|{}>{}|{:6.2f}%'.format(((20*i)//l)*'-', (19-(20*i)//l)*' ', 100 * ((i+1) / l)), end='' if i != l-1 else '\n') # show process bar
        end_t = time.time()
        dt = dt[np.where(dt['Weight'] > 0)]
        dset = opt.create_dataset('Answer', data=dt, compression='gzip')
        dset.attrs['totalTime'] = end_t - start_t
        dset.attrs['totalLength'] = l
        dset.attrs['spePath'] = aver_spe_path
        print('The output file path is {}'.format(fopt), end=' ', flush=True)
    return 

if __name__ == '__main__':
    main(args.opt, args.ipt, args.ref)