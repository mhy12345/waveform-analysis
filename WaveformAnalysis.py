from IPython import embed #ipython breakpoint inserting
import numpy as np
import re

import torch
import torch.utils.data as Data
from torch.nn import functional as F

from JPwaptool_Lite import JPwaptool_Lite, TreeWriter

import os,sys
import time

import tables

# Make Saving_Directory
NetDir = sys.argv[1]
fullfilename = sys.argv[2]
SavePath = sys.argv[3]
fileno=-int(sys.argv[-1])-1
if not os.path.exists(SavePath):
    os.makedirs(SavePath)

#detecting cuda device and wait in line
if torch.cuda.is_available():
    from Cuda_Queue import *
    while not QueueUp(fileno) : continue # append fileno to waiting list (first line of .bulletin.swp)
    device=wait_in_line(fileno,1024*1024*1024*1.5,0.3)
    torch.cuda.set_device(device)
    device=torch.device(device)
else : 
    device = 'cpu'
    print('Using device: cpu')
    
# begin loading
#Neural Networks
from CNN_Module import Net_1

fileSet = os.listdir(NetDir)
matchrule = re.compile(r"_epoch(\d+)_loss(\d+(\.\d*)?|\.\d+)([eE]([-+]?\d+))?")
NetLoss_reciprocal = []
for filename in fileSet :
    if "_epoch" in filename : NetLoss_reciprocal.append(1/float(matchrule.match(filename)[2]))
    else : NetLoss_reciprocal.append(0)
net_name = fileSet[NetLoss_reciprocal.index(max(NetLoss_reciprocal))]
net = torch.load(NetDir+net_name,map_location=device)#Pre-trained Model Parameters

# Data Settings
LoadingPeriod= 20000

# Create the output file
outputfile = TreeWriter(SavePath+"Prediction.root")

# Loading Data
RawDataFile =  tables.open_file(fullfilename)
Data_set = RawDataFile.root.Waveform
WindowSize = len(Data_set[0]['Waveform'])
if WindowSize>=1000 :
    stream = JPwaptool_Lite(WindowSize,100,600)
elif WindowSize==600 :
    stream = JPwaptool_Lite(WindowSize,50,400)
else : 
    raise ValueError("Unknown WindowSize, I don't know how to choose the parameters for pedestal calculatation")
Total_entries = len(Data_set)
print(Total_entries)

# Prepare for data and generating answer from prediction
filter_limit = 0.9/WindowSize 
Timeline = torch.arange(WindowSize,device=device).repeat([LoadingPeriod,1])
entryList = np.arange(0,Total_entries,LoadingPeriod)
entryList = np.append(entryList,Total_entries)
start_time = time.time()
# Loop for batched data
for k in range(len(entryList)-1) :
    # Making Dataset
    EventData = Data_set[entryList[k]:entryList[k+1]]['EventID']
    ChanData = Data_set[entryList[k]:entryList[k+1]]['ChannelID']
    WaveData = Data_set[entryList[k]:entryList[k+1]]['Waveform']
    inputs = torch.empty((len(WaveData),WindowSize),device=device)
    for i in range(len(WaveData)) :
        stream.Calculate(WaveData[i])
        inputs[i] = torch.from_numpy(stream.ChannelInfo.Ped - WaveData[i])
    # Make mark
    print("Processing entry {0}, Progress {1}%".format(k*LoadingPeriod,k*LoadingPeriod/Total_entries*100))
    
    if len(EventData)!=len(Timeline) : 
        Timeline = torch.arange(WindowSize,device=device).repeat([len(EventData),1])
    
    if k==0 :
        if device!='cpu' :
            ## finish loading to GPU, give tag on .bulletin.swp
            os.system("echo {} {} >> .bulletin.swp".format(fileno,0))
    
    #calculating
    Prediction = net(inputs).data
    # checking for no pe event
    PETimes = Prediction>filter_limit
    pe_numbers = PETimes.sum(1)
    no_pe_found = pe_numbers==0 
    if no_pe_found.any() :
        print("I cannot find any pe in Event {0}, Channel {1} (entry {2})".format(EventData[no_pe_found.cpu().numpy()],ChanData[no_pe_found.cpu().numpy()],k*LoadingPeriod+np.arange(LoadingPeriod)[no_pe_found.cpu().numpy()]))
        guessed_petime = F.relu(inputs[no_pe_found].max(1)[1]-7)
        PETimes[no_pe_found,guessed_petime] = True
        Prediction[no_pe_found,guessed_petime] = 1
        pe_numbers[no_pe_found] = 1
    
    # Makeing Output and write submission file
    Weights = Prediction[PETimes].cpu().numpy()
    PETimes = Timeline[PETimes].cpu().numpy()
    pe_numbers = pe_numbers.cpu().numpy()
    EventData = np.repeat(EventData,pe_numbers)
    ChanData = np.repeat(ChanData,pe_numbers)
    outputfile.Fill(EventData,ChanData,PETimes)
        
# Flush into the output file
outputfile.Write()


RawDataFile.close()
end_time=time.time()
print("Prediction_Generated")

toc = end_time-start_time #~1200s 20min
print("Time of Computing",toc)