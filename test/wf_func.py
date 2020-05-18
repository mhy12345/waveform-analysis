# -*- coding: utf-8 -*-

import os
import math
import numpy as np
from scipy import optimize as opti
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import h5py
import torch
import pyro
import pyro.distributions as dist
from pyro.infer.mcmc import MCMC, NUTS
from pyro.infer.mcmc.util import initialize_model

device = torch.device(0)

def fit_N(wave, spe_pre, method, model=None, return_position=False):
    l = wave.shape[0]
    spe_l = spe_pre['spe'].shape[0] 
    n = math.ceil(spe_l//10)
    difth = np.sort(spe_pre['spe'][np.arange(2,spe_l-1)+1]-spe_pre['spe'][np.arange(2,spe_l-1)]-spe_pre['spe'][np.arange(2,spe_l-1)-1]+spe_pre['spe'][np.arange(2,spe_l-1)-2])[n]
    lowp = np.argwhere(vali_base(wave, spe_pre['m_l'], spe_pre['thres']) == 1).flatten()
    lowp = lowp[np.logical_and(lowp > 1, lowp < l-1)]
    flag = 1
    if len(lowp) != 0:
        panel = np.zeros(l)
        for j in lowp:
            head = j-spe_pre['mar_l'] if j-spe_pre['mar_l'] > 0 else 0
            tail = j+spe_pre['mar_r'] if j+spe_pre['mar_r'] <= l else l
            panel[head : tail + 1] = 1
        fitp = np.argwhere(panel == 1).flatten()
        numb = np.argwhere(wave[lowp+1]-wave[lowp]-wave[lowp-1]+wave[lowp-2] < difth).flatten()
        if len(numb) != 0:
            ran = np.arange(spe_pre['peak_c'] - 1, spe_pre['peak_c'] + 2)
            possible = np.unique(lowp[numb] - ran.reshape(ran.shape[0], 1))
            possible = possible[np.logical_and(possible>=0, possible<l)]
            if len(possible) != 0:
                if method == 'xiaopeip':
                    pf_r = xiaopeip_core(wave, spe_pre['spe'], fitp, possible)
            else:
                flag = 0
        else:
            flag = 0
    else:
        flag = 0
    if flag == 0:
        t = np.where(wave == wave.min())[0][:1] - spe_pre['peak_c']
        possible = t if t[0] >= 0 else np.array([0])
        pf_r = np.array([1])
    pf = np.zeros_like(wave)
    pf[possible] = pf_r
    if return_position:
        return pf, fitp, possible
    else:
        return pf

def xiaopeip_core(wave, spe, fitp, possible):
    l = wave.shape[0]
    spe = np.concatenate([spe, np.zeros(l - spe.shape[0])])
    ans0 = np.zeros_like(possible).astype(np.float64)
    b = np.zeros((possible.shape[0], 2)).astype(np.float64)
    b[:, 1] = np.inf
    mne = spe[np.mod(fitp.reshape(fitp.shape[0], 1) - possible.reshape(1, possible.shape[0]), l)]
    ans = opti.fmin_l_bfgs_b(norm_fit, ans0, args=(mne, wave[fitp]), approx_grad=True, bounds=b, maxfun=500000)
    # ans = opti.fmin_slsqp(norm_fit, ans0, args=(mne, wave[fitp]), bounds=b, iprint=-1, iter=500000)
    # ans = opti.fmin_tnc(norm_fit, ans0, args=(mne, wave[fitp]), approx_grad=True, bounds=b, messages=0, maxfun=500000)
    pf_r = ans[0]
    return pf_r

def lucyddm_core(waveform, spe, iterations=100):
    '''Lucy deconvolution
    Parameters
    ----------
    waveform : 1d array
    spe : 1d array
        point spread function; single photon electron response
    iterations : int

    Returns
    -------
    signal : 1d array

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Richardson%E2%80%93Lucy_deconvolution
    .. [2] https://github.com/scikit-image/scikit-image/blob/master/skimage/restoration/deconvolution.py#L329
    '''
    wave = np.where(waveform > 0, waveform, 0)
    wave = wave + 0.001
    wave = wave / np.sum(spe)
    t = np.argwhere(spe > 0)[0][0]
    spe_t = spe[spe > 0]
    l = spe_t.shape[0]
    # use the deconvlution method
    wave_deconv = np.full(wave.shape, 0.1)
    spe_mirror = spe_t[::-1]
    for _ in range(iterations):
        relative_blur = wave / np.convolve(wave_deconv, spe_t, 'same')
        wave_deconv = wave_deconv * np.convolve(relative_blur, spe_mirror, 'same')
        # there is no need to set the bound if the spe and the wave are all none negative
    wave_deconv = np.append(wave_deconv[(l-1)//2+t:], np.zeros((l-1)//2+t))
    # np.convolve(wave_deconv, spe, 'full')[:len(wave)] should be wave
    wave_deconv = np.where(wave_deconv<50, wave_deconv, 0)
    return wave_deconv

def mcmc_core(wave, spe_pre, model, return_position=False):
    l = len(wave); spe = torch.tensor(spe_pre['spe']).float(); wave = torch.tensor(wave).float()
    spe = torch.cat((spe, torch.zeros(l - len(spe))))
    pos = (wave > spe_pre['thres']).nonzero().flatten() - (spe_pre['peak_c'] + 2)
    pos = pos[torch.logical_and(pos >= 0, pos < l)]
    def model(n, mne, sigma):
        pf = pyro.sample('weight', dist.HalfNormal(torch.ones(n)))
        y = pyro.sample('y', dist.Normal(0, sigma), obs=wave - torch.matmul(mne, pf))
        return y
    flag = 1
    if len(pos) == 0:
        flag = 0
    else:
        nuts_kernel = NUTS(model, step_size=0.01, adapt_step_size=True)
        mne = spe[torch.remainder(torch.arange(l).reshape(l, 1) - pos.reshape(1, len(pos)), l)]
        mcmc = MCMC(nuts_kernel, num_samples=50, warmup_steps=100)
        mcmc.run(len(pos), mne, 0.5)
        pf_r = mcmc.get_samples()['weight']
        pf_r = pf_r[torch.tensor([norm_fit_tensor(pf_r[i], mne, wave, eta=spe.sum()/2) for i in range(100)]).argmin()]
        pos = pos[(pf_r > 0.05).nonzero().flatten()]
        if len(pos) == 0:
            flag = 0
        else:
            init_param = {'weight' : torch.where(pf_r > 0.05)}
            mne = spe[torch.remainder(torch.arange(l).reshape(l, 1) - pos.reshape(1, len(pos)), l)]
            mcmc = MCMC(nuts_kernel, num_samples=100, warmup_steps=500, initial_params=init_param)
            mcmc.run(len(pos), mne, 0.1)
            pf_r = mcmc.get_samples()['weight']
            pf_r = pf_r[torch.tensor([norm_fit_tensor(pf_r[i], mne, wave, eta=spe.sum()/2) for i in range(500)]).argmin()]
            pos_r = pos.numpy()
            pf_r = pf_r.numpy()
    if flag == 0:
        t = (wave == wave.min()).nonzero()[0] - spe_pre['peak_c']
        pos_r = t if t[0] >= 0 else np.array([0])
        pf_r = np.array([1])
    pf = np.zeros_like(wave)
    pf[pos_r] = pf_r
    if return_position:
        return pf, pos_r
    else:
        return pf
        # mne = spe[np.mod(np.arange(l).reshape(l, 1) - pos.reshape(1, len(pos)), l)]
        # op = model.sampling(data=dict(m=mne, y=wave, Nf=l, Np=pos.shape[0]), iter=it, seed=0)
        # pf_r = op['x'][np.argmin([norm_fit(op['x'][i], mne, wave, eta=spe.sum()/2) for i in range(it)])]

def xpp_convol(pet, wgt):
    core = np.array([0.9, 1.7, 0.9])
    idt = np.dtype([('PETime', np.int16), ('Weight', np.float16), ('Wgt_b', np.uint8)])
    seg = np.zeros(np.max(pet) + 3, dtype=idt)
    seg['PETime'] = np.arange(-1, np.max(pet) + 2)
    seg['Weight'][np.sort(pet) + 1] = wgt[np.argsort(pet)]
    seg['Wgt_b'] = np.around(seg['Weight'])
    resi = seg['Weight'][1:-1] - seg['Wgt_b'][1:-1]
    t = np.convolve(resi, core, 'full')
    ta = np.diff(t, prepend=t[0])
    tb = np.diff(t, append=t[-1])
    seg['Wgt_b'][(ta > 0)*(tb < 0)*(t > 0.5)*(seg['Wgt_b'] == 0.0)*(seg['Weight'] > 0)] += 1
    if np.sum(seg['Wgt_b'][1:-1] > 0) != 0:
        pwe = seg['Wgt_b'][1:-1][seg['Wgt_b'][1:-1] > 0]
        pet = seg['PETime'][1:-1][seg['Wgt_b'][1:-1] > 0]
    else:
        pwe = np.array([1])
        pet = seg['PETime'][np.argmax(seg['Weight'])]
    return pet, pwe

def norm_fit_tensor(x, M, y, eta=0):
    return torch.pow(y - torch.matmul(M, x), 2).sum() + eta * x.sum()

def norm_fit(x, M, y, eta=0):
    return np.power(y - np.matmul(M, x), 2).sum() + eta * x.sum()

def read_model(spe_path):
    with h5py.File(spe_path, 'r', libver='latest', swmr=True) as speFile:
        spe = speFile['SinglePE'].attrs['SpePositive']
        epulse = speFile['SinglePE'].attrs['Epulse']
        thres = speFile['SinglePE'].attrs['Thres']
        m_l = np.sum(spe > thres)
        peak_c = np.argmax(spe)
        mar_l = np.sum(spe[:peak_c] < thres)
        mar_r = np.sum(spe[peak_c:] < thres)
    spe_pre = {'spe':spe, 'epulse':epulse, 'peak_c':peak_c, 'm_l':m_l, 'mar_l':mar_l, 'mar_r':mar_r, 'thres':thres}
    return spe_pre

def snip_baseline(waveform, itera=20):
    wm = np.min(waveform)
    waveform = waveform - wm
    v = np.log(np.log(np.sqrt(waveform+1)+1)+1)
    N = waveform.shape[0]
    for i in range(itera):
        v[i:N-i] = np.minimum(v[i:N-i], (v[:N-2*i] + v[2*i:])/2)
    w = np.power(np.exp(np.exp(v) - 1) - 1, 2) - 1 + wm
    return w

def vali_base(waveform, m_l, thres):
    m = np.median(waveform[waveform < np.median(waveform)])
    vali = np.where(waveform - m > thres, 1, 0) # valid waveform, not dark noise
    pos = omi2pos(vali)
    pos = rm_frag(pos, m_l)
    vali = pos2omi(pos, waveform.shape[0])
    return vali

def deduct_base(waveform, m_l=None, thres=None, itera=20, mode='fast'):
    wave = waveform - np.min(waveform)
    baseline = snip_baseline(wave, itera)
    wave = wave - baseline
    if mode == 'detail':
        wave = wave - find_base(wave, m_l, thres)
    elif mode == 'fast':
        wave = wave - find_base_fast(wave)
    return wave

def find_base(waveform, m_l, thres):
    vali = vali_base(waveform, m_l, thres)
    base_line = np.mean(waveform[vali == 0])
    return base_line

def find_base_fast(waveform):
    m = np.median(waveform[waveform < np.median(waveform)])
    base_line = np.mean(waveform[np.logical_and(waveform < m + 4, waveform > m - 4)])
    return base_line

def omi2pos(vali):
    vali_t = np.concatenate((np.array([0]), vali, np.array([0])), axis=0)
    dval = np.diff(vali_t)
    pos_begin = np.argwhere(dval == 1).flatten()
    pos_end = np.argwhere(dval == -1).flatten()
    pos = np.concatenate((pos_begin.reshape(pos_begin.shape[0], 1), pos_end.reshape(pos_end.shape[0], 1)), axis = 1).astype(np.int16)
    return pos

def pos2omi(pos, len_n):
    vali = np.zeros(len_n).astype(np.int16)
    for i in range(pos.shape[0]):
        vali[pos[i][0]:pos[i][1]] = 1
    return vali

def rm_frag(pos, m_l):
    n = pos.shape[0]
    pos_t = []
    for i in range(n):
        if pos[i][1] - pos[i][0] > m_l//3:
            pos_t.append(pos[i])
    pos = np.array(pos_t)
    return pos

def pf_to_tw(pf, thres=0.1):
    assert thres < 1, 'thres is too large, which is {}'.format(thres)
    if np.max(pf) < thres:
        t = np.argmax(pf)
        pf = np.zeros_like(pf)
        pf[t] = 1
    pwe = pf[pf > thres]
    pwe = pwe
    pet = np.argwhere(pf > thres).flatten()
    return pet, pwe
