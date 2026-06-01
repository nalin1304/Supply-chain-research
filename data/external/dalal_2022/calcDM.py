# -*- coding: utf-8 -*-
"""
Created on Mon Aug 30 13:57:18 2021

@author: J. Dalal
"""

import requests
import json

import os

import pandas as pd
import pulp as p
import numpy as np

from csv import DictWriter


## This subroutine fetches driving distance between location 1 (Lat_1, Lon_1) and location 2 (Lat_2, Lon_2)
def getDrivingDist(Lat_1, Lon_1, Lat_2, Lon_2):
    r = requests.get(f"http://router.project-osrm.org/route/v1/car/{Lon_1},{Lat_1};{Lon_2},{Lat_2}?overview=false""", timeout=5)
    
    routes = json.loads(r.content)
    route_1 = routes.get("routes")[0]
    d = float(route_1['distance'])/1000.0   ## convert from meters to kilometers
    r.close()
    return d


## read input file 1 - customer data set  
cust_records_All = pd.read_excel('DataSet.xlsx', sheet_name='Customer DataSet')
cust_recordList = cust_records_All.values

 

custCollection = []

for record in cust_recordList:

# make a dictionary for each customer, and enter that into the collection...
    
    custDictionary = {}
    custDictionary['Name'] = record[0]
    custDictionary['State'] = record[1]
    custDictionary['Zip'] = record[2]
    custDictionary['LatVal'] = record[3]
    custDictionary['LongVal'] = record[4]
    custDictionary['Demand_elec'] = record[5]
    custDictionary['Demand_appa'] = record[6]
    custDictionary['Demand_groc'] = record[7]
    custDictionary['Demand_book'] = record[8]
    
    
    custCollection.append(custDictionary)
    
    
    
# Get the list of all files and directories
path = "./infiles/"
dir_list = os.listdir(path)
 
  
  

for in_fileName in dir_list:  
    
    WH_records_All = pd.read_excel("./infiles/"+in_fileName, sheet_name='Sheet1')
    WH_list = WH_records_All.values

    WH_collection = []


    for record in WH_list:   
        whDictionary = {}
        whDictionary['Name'] = record[0]
        whDictionary['LatVal'] = record[1]
        whDictionary['LongVal'] = record[2]
        WH_collection.append(whDictionary)
   
    wh_wise_dist_dict = {}    

    for wh in WH_collection:
        lat_1 = wh['LatVal']
        long_1 = wh['LongVal']
        dist_from_wh = []
        for cust in custCollection:
            lat_2 = cust['LatVal']
            long_2 = cust['LongVal']
            
            dist_ij = getDrivingDist(lat_1,long_1,lat_2,long_2)
            print('Driving dist from warehouse '+ wh['Name']+ ' to Customer '+ cust['Name']+' is = '+ str(dist_ij) + ' km.')
            dist_from_wh.append(dist_ij)
            
        wh_wise_dist_dict[wh['Name']] = dist_from_wh
    
    print(wh_wise_dist_dict)

    out_fileName = in_fileName.split(".")[0] +"_DM.xlsx"
 
    df1 = pd.DataFrame.from_dict(wh_wise_dist_dict)
    df1.to_excel("./outfiles/"+ out_fileName)            ## you need to create a directory "outfiles" beforehand
 



    