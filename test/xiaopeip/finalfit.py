# -*- coding: utf-8 -*-

import re
import numpy as np
from scipy import optimize as opti
import h5py
import sys
sys.path.append('test')
import matplotlib.pyplot as plt
import math
import argparse
import wf_analysis_func as wfaf

psr = argparse.ArgumentParser()
psr.add_argument('-o', dest='opt', help='output file')
psr.add_argument('ipt', help='input file')
psr.add_argument('--ref', dest='ref', help='reference file')
psr.add_argument('--num', type=int, help='fragment number')
psr.add_argument('-p', dest='print', action='store_false', help='print bool', default=True)
args = psr.parse_args()

if args.print:
    sys.stdout = None

def norm_fit(x, M, p):
    return np.linalg.norm(p - np.matmul(M, x))

def main(fopt, fipt, single_pe_path):
    epulse = wfaf.estipulse(fipt)
    spemean = wfaf.generate_model(single_pe_path, epulse)
    spemean = -1 * epulse * spemean
    peak_c, zero_l, mar_l, mar_r, thres = wfaf.pre_analysis(fipt, epulse, spemean)

    opdt = np.dtype([('EventID', np.uint32), ('ChannelID', np.uint32), ('PETime', np.uint16), ('Weight', np.float16)])

    with h5py.File(fipt, 'r', libver='latest', swmr=True) as ipt:
        ent = ipt['Waveform']
        lenfr = math.floor(len(ent)/(args.num+1))
        num = int(re.findall(r'-\d+\.h5', fopt, flags=0)[0][1:-3])
        if (num+2)*lenfr > len(ent):
            ent = ent[num*lenfr:]
        else:
            ent = ent[num*lenfr:(num+1)*lenfr]

        Length_pe = len(ent[0]['Waveform'])
        assert Length_pe >= len(spemean), 'Single PE too long which is {}'.format(len(spemean))
        spemean = np.concatenate([spemean, np.zeros(Length_pe - len(spemean))])
        l = len(ent)
        print('{} waveforms will be computed'.format(l))
        dt = np.zeros(l * (Length_pe//5), dtype=opdt)
        start = 0
        end = 0
        for i in range(l):
            wf_input = ent[i]['Waveform']
            wf_input = -1 * epulse * wf_input
            #wave = wf_input - wfaf.find_base_fast(wf_input)
            wave = wf_input - wfaf.find_base(wf_input, zero_l)
            lowp = np.argwhere(wfaf.vali_base(wave, zero_l) == 1)
            lowp = np.argwhere(wave < thres).flatten()
            flag = 1
            lowp = lowp[np.logical_and(lowp > 1, lowp < Length_pe-1)]
            if len(lowp) != 0:
                panel = np.zeros(Length_pe)
                for j in lowp:
                    head = j-mar_l if j-mar_l > 0 else 0
                    tail = j+mar_r+1 if j+mar_r+1 <= Length_pe else Length_pe
                    panel[head:tail] = 1
                nihep = np.argwhere(panel == 1).flatten()
                xuhao = np.argwhere(wave[lowp+1]-wave[lowp]-wave[lowp-1]+wave[lowp-2] > 1.5).flatten()
                if len(xuhao) != 0:
                    possible = np.unique(np.concatenate((lowp[xuhao]-(peak_c+2), lowp[xuhao]-(peak_c+1), lowp[xuhao]-peak_c, lowp[xuhao]-(peak_c-1))))
                    possible = possible[np.logical_and(possible>=0, possible<Length_pe)]
                    if len(possible) != 0:
                        ans0 = np.zeros_like(possible).astype(np.float64)
                        b = np.zeros((len(possible), 2))
                        b[:, 1] = np.inf
                        mne = spemean[np.mod(nihep.reshape(len(nihep), 1) - possible.reshape(1, len(possible)), Length_pe)]
                        ans = opti.fmin_l_bfgs_b(norm_fit, ans0, args=(mne, wave[nihep]), approx_grad=True, bounds=b, maxfun=100000)
                        #ans = opti.fmin_slsqp(norm_fit, ans0, args=(mne, wave[nihep]), bounds=b, iprint=-1)
                        #ans = opti.fmin_tnc(norm_fit, ans0, args=(mne, wave[nihep]), approx_grad=True, bounds=b, messages=0, maxfun=10000)
                        pf = ans[0]
                        if np.sum(pf <= 0.1) == len(pf):
                            flag = 0
                    else:
                        flag = 0
                else:
                    flag = 0
            else:
                flag = 0
            if flag == 0:
                t = np.where(wave == wave.min())[0][:1] - np.argmin(spemean)
                possible = t if t[0] >= 0 else np.array([0])
                pf = np.array([1])
            pwe = pf[pf > 0.1]
            pwe = pwe.astype(np.float16)
            lenpf = len(pwe)
            pet = possible[pf > 0.1]
            end = start + lenpf
            dt['PETime'][start:end] = pet
            dt['Weight'][start:end] = pwe
            dt['EventID'][start:end] = ent[i]['EventID']
            dt['ChannelID'][start:end] = ent[i]['ChannelID']
            start = end
            print('\rAnsw Generating:|{}>{}|{:6.2f}%'.format(((20*i)//l)*'-', (19-(20*i)//l)*' ', 100 * ((i+1) / l)), end='' if i != l-1 else '\n')
    dt = dt[dt['Weight'] > 0]
    dt = np.sort(dt, kind='stable', order=['EventID', 'ChannelID', 'PETime'])
    with h5py.File(fopt, 'w') as opt:
        dset = opt.create_dataset('Answer', data=dt, compression='gzip')
        print('The output file path is {}'.format(fopt), end=' ', flush=True)
    return

def omi2pos(vali):
    vali_t = np.concatenate((np.array([0]), vali, np.array([0])), axis=0)
    dval = np.diff(vali_t)
    pos_begin = np.argwhere(dval == 1).flatten()
    pos_end = np.argwhere(dval == -1).flatten()
    pos = np.concatenate((pos_begin.reshape(len(pos_begin), 1), pos_end.reshape(len(pos_end), 1)), axis = 1).astype(np.int32)
    return pos

def pos2omi(pos, len_n):
    vali = np.zeros(len_n).astype(np.int32)
    for i in range(len(pos)):
        vali[pos[i][0]:pos[i][1]] = 1
    return vali

def rm_frag(pos, fl):
    n = len(pos)
    pos_t = []
    for i in range(n):
        if pos[i][1] - pos[i][0] > fl:
            pos_t.append(pos[i])
    pos = np.array(pos_t)
    return pos

if __name__ == '__main__':
    main(args.opt, args.ipt, args.ref)
