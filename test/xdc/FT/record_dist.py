import numpy as np
import csv
import h5py
import argparse

psr = argparse.ArgumentParser()
psr.add_argument('-o', dest='opt', help='output')
psr.add_argument('ipt', help='input')
args = psr.parse_args()

if __name__ == '__main__':
    with h5py.File(args.ipt, 'r') as distfile:
        dt = distfile['Record']
        l = len(dt)
        spePath = dt.attrs['spePath']
        totTime = dt.attrs['totalTime']
        totLen = dt.attrs['totalLength']
        wd = dt['wdist'].mean()
        pd = dt['pdist'].mean()
    with open(args.ipt, 'w+') as csvf:
        csvwr = csv.writer(csvf)
        csvwr.writerow([spePath, args.ipt, str(totTime), str(totLen), str(wd), str(pd)])
