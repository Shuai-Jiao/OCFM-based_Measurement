import matplotlib
import pm4py
import os
import tempfile
from pm4py.visualization.common import gview
from graphviz import Source
from pm4py.util import exec_utils
import matplotlib.pyplot as plt
import numpy as np
import math
import itertools
from pm4py.visualization.footprints import visualizer as fp_visualizer
from pm4py.algo.discovery.footprints import algorithm as footprints_discovery
import datetime
import pandas as pd
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.petri_net.utils import petri_utils
import pm4py
from pm4py.visualization.common import gview


def ParsingCSV(csvpath, parameters=None):
    csvlog = pd.read_csv(csvpath,sep=';')
    for ot in parameters['object_type']:
        csvlog[ot] = csvlog[ot].map(lambda x: str([y.strip() for y in x.split(',')]) if isinstance(x,str) else str([]))
        
    csvlog["event_id"] = list(range(0,len(csvlog)))
    csvlog.index = list(range(0,len(csvlog)))
    csvlog["event_id"] = csvlog["event_id"].astype(float).astype(int)
    csvlog = csvlog.rename(columns={"event_id": 'ocel:eid', parameters['time_name']:'ocel:timestamp',\
    parameters['act_name']:'ocel:activity'})
    for ot in parameters['object_type']:
        csvlog = csvlog.rename(columns={ot:str('ocel:type:'+ot)})
    '''Warnining: the previous timestamp should be determined whether an integer is'''
    csvlog['ocel:timestamp'] = [str(datetime.datetime.fromtimestamp(x))\
                                for x in csvlog['ocel:timestamp']]
    return csvlog

def OCEL2OCFM(ocel):
    otlist = pm4py.ocel_get_object_types(ocel)
    flatocfmlist = {}
    for ot in otlist:
        flatlog = pm4py.ocel_flattening(ocel, ot)
        flatocfm = footprints_discovery.apply(flatlog, variant=footprints_discovery.Variants.ENTIRE_EVENT_LOG)
        flatocfmlist[ot] = flatocfm
    return flatocfmlist


def GetOCPN(ocpn):
    integ = {'places':[],'transitions':[],'arcs':[]}
    for ot in ocpn['object_types']:
        integ['places'] += ocpn['petri_nets'][ot][0]['places']
        integ['transitions'] += ocpn['petri_nets'][ot]['transitions']
        integ['arcs'] += ocpn['petri_nets'][ot]['arcs']
        #integ['places'] += ocpn['petri_nets'][ot]['places']
    return integ


def decomposeOCPN(model):
    modellist = {}
    for key in model['petri_nets'].keys():
        net = model['petri_nets'][key][0]
        im = model['petri_nets'][key][1]
        fm = model['petri_nets'][key][2]
        demodel = (net,im,fm)
        modellist[key] = demodel
    return modellist


def OCPN2OCFM(ocpnlist):
    ocfmlist = {}
    for ot, ocpn in ocpnlist.items():
        ocfm = footprints_discovery.apply(ocpn[0], ocpn[1], ocpn[2])   
        ocfmlist[ot] = ocfm
    return ocfmlist


def MergeOCFM(ocfmlist,variablity = False):
    UNKNOWN_SYMBOL = "&#63;"
    XOR_SYMBOL = "&#35;"
    PREV_SYMBOL = "&#60;"
    SEQUENCE_SYMBOL = "&#62;"
    PARALLEL_SYMBOL = "||"
    
    activities = []
    for ot,ocfm in ocfmlist.items():
        #print(ocfm)
        activities = sorted(list(set(activities)|set(ocfm['activities'])))
    filename = tempfile.NamedTemporaryFile(suffix='.gv')
    
    integratedtable = ["digraph {\n", "tbl [\n", "shape=plaintext\n", "label=<\n"]
    integratedtable.append("<table border='0' cellborder='1' color='blue' cellspacing='0'>\n")
    integratedtable.append("<tr><td></td>")
    for act in activities:
        integratedtable.append("<td><b>"+act+"</b></td>")
    integratedtable.append("</tr>\n")
    for a1 in activities:
        integratedtable.append("<tr><td><b>"+a1+"</b></td>")
        for a2 in activities:
            symb_1 = "?"
            symb_2 = "?"
            relation = "{"
            conflict = True
            for ot, ocfm in ocfmlist.items():
                '''if a1 in activities and a2 in activities:
                    symb_1 = XOR_SYMBOL'''
                if (a1, a2) in ocfm["parallel"]:
                    symb_1 = PARALLEL_SYMBOL
                    conflict = False
                elif (a1, a2) in ocfm["sequence"]:
                    symb_1 = SEQUENCE_SYMBOL
                    conflict = False
                elif (a2, a1) in ocfm["sequence"]:
                    symb_1 = PREV_SYMBOL
                    conflict = False
                else:
                    continue
                symb = symb_1+"<sup>"+ot+"</sup>"
                relation += (symb+',')
            if conflict == True:
                relation = XOR_SYMBOL
            else:
                relation = relation[:-1]+'}'
            integratedtable.append("<td><font color=\"black\">"+ relation +"</font></td>")
        integratedtable.append("</tr>\n")
    integratedtable.append("</table>\n")
    integratedtable.append(">];\n")
    integratedtable.append("}\n")

    integratedtable = "".join(integratedtable)
    
    image_format = exec_utils.get_param_value("format", None, "png")
    gviz = Source(integratedtable, filename=filename.name)
    gviz.format = image_format

    return gviz

def EvalOCFM(logocfm,modelocfm): #ocfm1 and ocfm2 are both lists
    nonconflicttotal, conform, _ = CompareOCFM(logocfm,modelocfm)
    fitness = conform/nonconflicttotal
    nonconflicttotal, conform, seqratio = CompareOCFM(modelocfm,logocfm)
    precision = conform/nonconflicttotal
    simplicity = 1-1/(1 + np.exp(-10*seqratio+7)) #offset to 7
    return fitness, precision, simplicity 
        
        
def CompareOCFM(conformed,conforming): # parameters are ocfm
    nonconflicttotal = 0
    conform = 0
    seq = 0
    activities = []
    
    for ot,ocfm in conformed.items():
        activities = sorted(list(set(activities)|set(ocfm['activities'])))
    allele = list(itertools.product(activities,activities))
    #total = len(list(conformed['activities'])**2
    conflictele = allele
                
    for ot1,ocfm1 in conformed.items():
        for pair1 in ocfm1['sequence']:
            for pair2 in conforming[ot1]['sequence']|conforming[ot1]['parallel']:
                if pair1 == pair2:
                    conform += 1
            conflictele = list(set(conflictele)-set([pair1]))
        
        for pair1 in ocfm1['parallel']:
            for pair2 in conforming[ot1]['parallel']:
                if pair1 == pair2:
                    conform += 1
            
            for pair2 in conforming[ot1]['sequence']:
                if pair1[0] == pair1[1]:
                    if pair1 == pair2:
                        conform += 1
                else:
                    if pair1 == pair2:
                        conform += 0.5
            conflictele = list(set(conflictele)-set([pair1]))
                    
        nonconflicttotal += (len(ocfm1['sequence'])+len(ocfm1['parallel']))           
        seq += len(ocfm1['sequence'])    
        
    return nonconflicttotal, conform, seq/(nonconflicttotal+len(conflictele))

def EvalbyOCFM(ocel,parameters=None):
    '''Suspended work'''
    if parameters == None:
        ocpn = pm4py.discover_oc_petri_net(ocel)
        ocpnlist = decomposeOCPN(ocpn)
        ocfm1 = OCPN2OCFM(ocpnlist)
        ocfm2 = OCEL2OCFM(ocel)
        print(EvalOCFM(ocfm1,ocfm2))
    else:
        raise ValueError("Parameter configuration is not done so far")


def Evaluation(ocel,ocpn):
    ocpnlist = decomposeOCPN(ocpn)
    ocfmmodel = OCPN2OCFM(ocpnlist)
    ocfmlog = OCEL2OCFM(ocel)
    gviz1=MergeOCFM(ocfmmodel)
    gviz2=MergeOCFM(ocfmlog)
    gview.view(gviz1)
    gview.view(gviz2)
    result = EvalOCFM(ocfmlog,ocfmmodel)
    return result

def Flowermodel(model):
    ocpn = model
    activitytype = {}
    for act in model['activities']:
        activitytype[act]=[]
        for ot in model['object_types']:
            for ele in list(model['petri_nets'][ot][0].transitions):
                if act==ele.label:
                    activitytype[act].append(ot)
    objecttype = model['object_types']
    
    places = {}
    transitions = {}
    im,fm = Marking(),Marking()
    for ot in objecttype:
        net = PetriNet(ot)
        places[ot] = PetriNet.Place(ot)
        net.places.add(places[ot])
        im[places[ot]] = 1
        fm[places[ot]] = 1
        
        for trans in activitytype.keys():
            for ot2 in activitytype[trans]: 
                if ot2 == ot:
                    transitions[trans] = PetriNet.Transition(trans,trans)
                    net.transitions.add(transitions[trans])
                    petri_utils.add_arc_from_to(places[ot],transitions[trans],net)
                    petri_utils.add_arc_from_to(transitions[trans],places[ot],net)    
        ocpn['petri_nets'][ot] = [net,im,fm]
    return ocpn

def Restrictedmodel(model,ocel):
    for ot in model['object_types']:
        flat_log = pm4py.ocel_flattening(ocel, ot)
        onetracelog = flat_log.loc[flat_log['case:concept:name'] == flat_log['case:concept:name'][0]]
        event_log = pm4py.convert_to_event_log(onetracelog)
        net, im, fm = pm4py.discover_petri_net_inductive(event_log)
        model['petri_nets'][ot] = (net,im,fm)
    return model



if __name__ == "__main__":
    path1 = '/Users/jiao.shuai.1998.12.01outlook.com/Documents/OCFM/OCEL/jsonocel/running-example.jsonocel'
    ocel1 = pm4py.read_ocel(path1)
    path2 = '/Users/jiao.shuai.1998.12.01outlook.com/Documents/OCFM/OCEL/example.csv'

    parameter1 = {'time_name':'event_timestamp','act_name':'event_activity','object_type':['order','item','delivery']}
    ParsingCSV(path2,parameter1).to_csv('./ocelexample.csv')
    ocel2 = pm4py.read_ocel('./ocelexample.csv')

    ocpn1 = pm4py.discover_oc_petri_net(ocel1)
    ocpn2 = pm4py.discover_oc_petri_net(ocel2)
    flower1 = Flowermodel(ocpn1)
    restricted1 = Restrictedmodel(ocpn1,ocel1)
    flower2 = Flowermodel(ocpn2)
    restricted2 = Restrictedmodel(ocpn2,ocel2)
    #pm4py.view_ocpn(ocpn1, format="png")
    #pm4py.view_ocpn(flower1, format="png")

    result1 = Evaluation(ocel1,ocpn1)
    result2 = Evaluation(ocel2,ocpn2)
    result3 = Evaluation(ocel1,flower1)
    result4 = Evaluation(ocel2,flower2)
    result5 = Evaluation(ocel1,restricted1)
    result6 = Evaluation(ocel2,restricted2)

    #list1 = [(path1,result1), (path2,result2),(path1,result3),(path2,result4)]
    list2 = [(path1,result1), (path1,result3),(path1,result5)]
    list3 = [(path2,result2), (path2,result4),(path2,result6)]

    for ele in list2+list3:
        print('The quality dimensions of',ele[0][7:],'compared to its discovered model are: ','\nThe fitness is: ',ele[1][0],'\nThe precision is: ',ele[1][1],'\nThe simplicity is: ',ele[1][2])


  