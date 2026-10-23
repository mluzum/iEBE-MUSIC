#!/usr/bin/env python3

import h5py
import sys
import pickle
import numpy as np
from scipy.interpolate import RegularGridInterpolator

EPS = 1e-15

NORDER = 9

weakFDFlag = True
weakString = ""
if weakFDFlag:
    weakString = "_weakFD"

initialFlag = False
pTdiffFlag = True
etadiffFlag = True
photonFlag = True

kinematicCutsDict = {
    "STAR_eta_-0p5_0p5_pT_0p2_4": {
        "pTmin": 0.2,
        "pTmax": 4,
        "etamin": -0.5,
        "etamax": 0.5
    },
    "STAR_eta_-1_-0p5_pT_0p2_4": {
        "pTmin": 0.2,
        "pTmax": 4,
        "etamin": -1,
        "etamax": -0.5
    },
    "STAR_eta_0p5_1_pT_0p2_4": {
        "pTmin": 0.2,
        "pTmax": 4,
        "etamin": 0.5,
        "etamax": 1
    },
    "STAR_eta_-1_1_pT_0p2_4": {
        "pTmin": 0.2,
        "pTmax": 4,
        "etamin": -1,
        "etamax": 1
    },
    "STAR_eta_-0p5_0p5_pT_0p2_2": {
        "pTmin": 0.2,
        "pTmax": 2,
        "etamin": -0.5,
        "etamax": 0.5
    },
    "STAR_eta_-1_-0p5_pT_0p2_2": {
        "pTmin": 0.2,
        "pTmax": 2,
        "etamin": -1,
        "etamax": -0.5
    },
    "STAR_eta_0p5_1_pT_0p2_2": {
        "pTmin": 0.2,
        "pTmax": 2,
        "etamin": 0.5,
        "etamax": 1
    },
    "STAR_eta_-0p5_0_pT_0p2_2": {
        "pTmin": 0.2,
        "pTmax": 2,
        "etamin": -0.5,
        "etamax": 0
    },
    "STAR_eta_0_0p5_pT_0p2_2": {
        "pTmin": 0.2,
        "pTmax": 2,
        "etamin": 0,
        "etamax": 0.5
    },
}

pidList = [('ch', '9999'), ('pi+', '211'), ('pi-', '-211'), ('K+', '321'),
           ('K-', '-321'), ('p', '2212'), ('pbar', '-2212')]

photonList = [
    'QGP_2to2_total',
    'QGP_AMYcollinear',
    'HG_2to2_meson_total',
    'HG_omega',
    'HG_rho_spectralfun',
    'HG_pipi_bremsstrahlung',
]

LHCetaRangeList = [
    '-0.4_0.4', '-0.5_0.5', '-0.8_-0.4', '-2.4_-0.5', '-2.5_-0.5', '-3.7_-1.7',
    '-4.9_-3.1', '-5.1_-2.8', '0.4_0.8', '0.5_2.4', '0.5_2.5', '1.7_3.7',
    '2.8_5.1', '3.1_4.9', '2.8_5.1'
]
RHICetaRangeList = ['-0.5_0.5', '-1_-0.5', '-3.9_-3.1', '0.5_1', '3.1_3.9']


def help_message():
    print("Usage: {0} database_file".format(sys.argv[0]))
    exit(0)


def get3DGlauberData(h5Event):
    """
        this function gets the 3D Glauber data from the hdf5 event
    """
    data = None
    for fileName in h5Event.keys():
        if "strings_" in fileName:
            data = h5Event.get(fileName).attrs.get("header")
            break
    if data is None:
        return [0.0, 0, 0, 0, 0, 0, 0]
    # normalize header to a single string
    if isinstance(data, (list, tuple, np.ndarray)):
        try:
            data_str = " ".join([
                d.decode("utf-8") if isinstance(d,
                                                (bytes, bytearray)) else str(d)
                for d in data
            ])
        except Exception:
            data_str = " ".join([str(d) for d in data])
    elif isinstance(data, (bytes, bytearray)):
        data_str = data.decode("utf-8")
    else:
        data_str = str(data)
    data = data_str.split()
    b = float(data[3])
    Npart = int(data[7])
    Ncoll = int(data[10])
    Nstrings = int(data[13])
    Etot = float(data[16])
    Pztot = float(data[20])
    randomSeed = int(data[24])
    return [b, Npart, Ncoll, Nstrings, Etot, Pztot, randomSeed]


def calcualte_inte_Vn_pT(pT_low, pT_high, data):
    """
        this function calculates the pT-integrated vn in a
        given pT range (pT_low, pT_high) for every event in the data
    """
    npT = 50
    pT_inte_array = np.linspace(pT_low, pT_high, npT)
    dpT = pT_inte_array[1] - pT_inte_array[0]
    dN_event = data[:, 1]
    totalN_event = data[:, -1]
    pT_event = data[:, 0]
    dN_interp = np.exp(
        np.interp(pT_inte_array, pT_event, np.log(dN_event + 1e-30)))
    totalN_interp = np.exp(
        np.interp(pT_inte_array, pT_event, np.log(totalN_event + 1e-30)))
    N = 2.*np.pi*np.sum(dN_interp*pT_inte_array)*dpT
    totalN = np.sum(totalN_interp)*dpT/(pT_event[1] - pT_event[0])
    meanpT = (np.sum(dN_interp*pT_inte_array**2.)
              /np.sum(dN_interp*pT_inte_array))
    temp_vn_array = [N, meanpT]
    for iorder in range(1, NORDER + 1):
        vn_real_event = data[:, 2*iorder]
        vn_imag_event = data[:, 2*iorder + 1]
        vn_real_interp = np.interp(pT_inte_array, pT_event, vn_real_event)
        vn_imag_interp = np.interp(pT_inte_array, pT_event, vn_imag_event)
        Vn_real_inte = (np.sum(vn_real_interp*dN_interp*pT_inte_array)
                        /np.sum(dN_interp*pT_inte_array))
        Vn_imag_inte = (np.sum(vn_imag_interp*dN_interp*pT_inte_array)
                        /np.sum(dN_interp*pT_inte_array))
        temp_vn_array.append(Vn_real_inte + 1j*Vn_imag_inte)
    temp_vn_array.append(totalN)
    return temp_vn_array


def calcualte_inte_Vn_eta(etaMin, etaMax, data, vnFlag=True):
    """
        this function calculates the eta-integrated vn in a
        given eta range (etaMin, etaMax) for every event in the data
    """
    nEta = 50
    eta_inte_array = np.linspace(etaMin, etaMax, nEta)
    deta = eta_inte_array[1] - eta_inte_array[0]
    dN_event = data[:, 1]
    ET_event = data[:, -2]
    totalN_event = data[:, -1]
    eta_event = data[:, 0]
    dN_interp = np.exp(
        np.interp(eta_inte_array, eta_event, np.log(dN_event + 1e-30)))
    totalN_interp = np.exp(
        np.interp(eta_inte_array, eta_event, np.log(totalN_event + 1e-30)))
    ET_interp = np.exp(
        np.interp(eta_inte_array, eta_event, np.log(ET_event + 1e-30)))
    N = np.sum(dN_interp)*deta
    totalN = np.sum(totalN_interp)*deta/(eta_event[1] - eta_event[0])
    ET = np.sum(ET_interp)*deta
    temp_vn_array = [N, ET]
    if vnFlag:
        for iorder in range(1, NORDER + 1):
            vn_real_event = data[:, 2*iorder + 1]
            vn_imag_event = data[:, 2*iorder + 2]
            vn_real_interp = np.interp(eta_inte_array, eta_event, vn_real_event)
            vn_imag_interp = np.interp(eta_inte_array, eta_event, vn_imag_event)
            Vn_real_inte = np.sum(vn_real_interp*dN_interp)/np.sum(dN_interp)
            Vn_imag_inte = np.sum(vn_imag_interp*dN_interp)/np.sum(dN_interp)
            temp_vn_array.append(Vn_real_inte + 1j*Vn_imag_inte)
        temp_vn_array.append(totalN)
    return temp_vn_array


def calcualte_inte_Vn_pTeta(pTMin, pTMax, etaMin, etaMax, data, Nevents):
    """
        this function calculates the pT and eta-integrated vn in a
        given pT range (pTMin, pTMax) and eta range (etaMin, etaMax)
        for every event in the data
    """
    # robust integration for possibly sparse pT-eta sampled data
    # expected columns: [eta, pT, dN, ... Qn real/imag ...]
    if data is None or len(data) == 0:
        return [0.0, 0.0] + [0 + 0j]*NORDER + [0.0]

    arr = np.array(data)
    ncols = arr.shape[1]
    # determine available max harmonic from columns
    max_order_available = 0
    if ncols > 4:
        max_order_available = int((ncols - 4) // 2)
    max_order = min(NORDER, max_order_available)

    # select rows within requested pT and eta ranges
    mask = (arr[:, 1] >= pTMin) & (arr[:, 1] <= pTMax) & (
        arr[:, 0] >= etaMin) & (arr[:, 0] <= etaMax)
    sel = arr[mask]
    if sel.size == 0:
        return [0.0, 0.0] + [0 + 0j]*max_order + [0.0]

    # group by eta
    etas = np.unique(sel[:, 0])
    N_eta = []
    meanpT_eta = []
    Vn_eta = [[] for _ in range(max_order)]
    for eta in etas:
        rows = sel[sel[:, 0] == eta]
        # sort by pT
        rows = rows[np.argsort(rows[:, 1])]
        pT_vals = rows[:, 1]
        dN_vals = rows[:, 2]
        # estimate dpT per pT point using neighboring differences
        if len(pT_vals) == 1:
            dp = np.array([1.0])
        else:
            dp = np.zeros_like(pT_vals)
            dp[1:-1] = 0.5*(pT_vals[2:] - pT_vals[:-2])
            dp[0] = pT_vals[1] - pT_vals[0]
            dp[-1] = pT_vals[-1] - pT_vals[-2]

        weight = dN_vals*pT_vals*dp
        N_eta_j = 2.*np.pi*np.sum(weight)
        N_eta.append(N_eta_j)
        if np.sum(weight) > 0:
            meanpT_eta.append(
                np.sum(dN_vals*pT_vals**2*dp)/np.sum(dN_vals*pT_vals*dp))
        else:
            meanpT_eta.append(0.0)

        for iorder in range(1, max_order + 1):
            idx_real = 2*iorder + 2
            idx_imag = 2*iorder + 3
            if idx_imag < ncols:
                Qn_real = rows[:, idx_real]
                Qn_imag = rows[:, idx_imag]
                # integrate Qn * dN * pT * dp
                num_real = np.sum(Qn_real*dN_vals*pT_vals*dp)
                num_imag = np.sum(Qn_imag*dN_vals*pT_vals*dp)
                denom = np.sum(dN_vals*pT_vals*dp) + EPS
                Vn_eta[iorder - 1].append(num_real/denom + 1j*(num_imag/denom))
            else:
                Vn_eta[iorder - 1].append(0.0 + 0.0j)

    # integrate over eta (simple trapezoidal on N_eta and weighted averages for Vn)
    etas_sorted = np.array(etas)
    N_eta = np.array(N_eta)
    meanpT_eta = np.array(meanpT_eta)
    totalN = np.trapz(N_eta, etas_sorted)
    if totalN <= 0:
        meanpT = 0.0
    else:
        meanpT = np.trapz(meanpT_eta*N_eta, etas_sorted)/totalN

    temp_vn_array = [totalN, meanpT]
    for iorder in range(1, NORDER + 1):
        if iorder <= max_order:
            Vn_list = np.array([v for v in Vn_eta[iorder - 1]])
            if Vn_list.size == 0:
                temp_vn_array.append(0.0 + 0.0j)
            else:
                weights = N_eta + EPS
                Vn_eta_mean = np.sum(Vn_list*weights)/np.sum(weights)
                temp_vn_array.append(Vn_eta_mean)
        else:
            temp_vn_array.append(0.0 + 0.0j)

    # append per-eta multiplicity (matching shape of N_eta) for compatibility
    temp_vn_array.append(N_eta*Nevents)
    return temp_vn_array


def calcualte_inte_Vneta_pTeta(pTMin: float, pTMax: float, data, Nevents: int,
                               weightType: int):
    """
        this function calculates the pT-integrated vn(eta) in a
        given pT range (pTMin, pTMax) for every event in the data
    """
    # robust eta-dependent integration for possibly sparse pT sampling
    if data is None or len(data) == 0:
        return [np.array([]), np.array([])
               ] + [np.array([]) for _ in range(NORDER)] + [0.0]

    arr = np.array(data)
    ncols = arr.shape[1]
    max_order_available = 0
    if ncols > 4:
        max_order_available = int((ncols - 4) // 2)
    max_order = min(NORDER, max_order_available)

    # select rows within pT range
    mask = (arr[:, 1] >= pTMin) & (arr[:, 1] <= pTMax)
    sel = arr[mask]
    if sel.size == 0:
        return [np.array([]), np.array([])
               ] + [np.array([]) for _ in range(NORDER)] + [0.0]

    etas = np.unique(sel[:, 0])
    N_eta = []
    meanpT_eta = []
    Vn_eta = [[] for _ in range(max_order)]
    for eta in etas:
        rows = sel[sel[:, 0] == eta]
        rows = rows[np.argsort(rows[:, 1])]
        pT_vals = rows[:, 1]
        dN_vals = rows[:, 2]
        if len(pT_vals) == 1:
            dp = np.array([1.0])
        else:
            dp = np.zeros_like(pT_vals)
            dp[1:-1] = 0.5*(pT_vals[2:] - pT_vals[:-2])
            dp[0] = pT_vals[1] - pT_vals[0]
            dp[-1] = pT_vals[-1] - pT_vals[-2]

        weight = dN_vals*pT_vals*dp
        N_eta_j = np.sum(weight)
        N_eta.append(N_eta_j)
        if np.sum(weight) > 0:
            meanpT_eta.append(
                np.sum(dN_vals*pT_vals**2*dp)/np.sum(dN_vals*pT_vals*dp))
        else:
            meanpT_eta.append(0.0)

        for iorder in range(1, max_order + 1):
            idx_real = 2*iorder + 2
            idx_imag = 2*iorder + 3
            if idx_imag < ncols:
                Qn_real = rows[:, idx_real]
                Qn_imag = rows[:, idx_imag]
                if weightType == 1:
                    num_real = np.sum(Qn_real*pT_vals*weight)
                    num_imag = np.sum(Qn_imag*pT_vals*weight)
                else:
                    num_real = np.sum(Qn_real*weight)
                    num_imag = np.sum(Qn_imag*weight)
                denom = np.sum(weight) + EPS
                Vn_eta[iorder - 1].append(num_real/denom + 1j*(num_imag/denom))
            else:
                Vn_eta[iorder - 1].append(0.0 + 0.0j)

    etas_sorted = np.array(etas)
    N_eta = np.array(N_eta)
    meanpT_eta = np.array(meanpT_eta)
    totalN = np.trapz(N_eta, etas_sorted)

    temp_vn_array = [N_eta, meanpT_eta]
    for iorder in range(1, NORDER + 1):
        if iorder <= max_order:
            temp_vn_array.append(np.array(Vn_eta[iorder - 1]))
        else:
            temp_vn_array.append(np.zeros_like(N_eta, dtype=complex))

    temp_vn_array.append(totalN*Nevents)
    return temp_vn_array


def calcualte_yield_and_meanpT(pT_low, pT_high, data):
    """
        this function calculates the pT-integrated particle yield and mean pT
        given pT range (pT_low, pT_high) for every event in the data
    """
    npT = 50
    pT_inte_array = np.linspace(pT_low, pT_high, npT)
    dpT = pT_inte_array[1] - pT_inte_array[0]
    dN_event = data[:, 1]
    pT_event = data[:, 0]
    dN_interp = np.exp(
        np.interp(pT_inte_array, pT_event, np.log(dN_event + 1e-30)))
    N = 2.*np.pi*np.sum(dN_interp*pT_inte_array)*dpT
    meanpT = (np.sum(dN_interp*pT_inte_array**2.)
              /np.sum(dN_interp*pT_inte_array))
    res_array = [N, meanpT]
    return res_array


try:
    database_file = str(sys.argv[1])
except IndexError:
    help_message()

h5_data = h5py.File(database_file, "r")
eventList = list(h5_data.keys())

outdata = {}

for ievent, event_i in enumerate(eventList):
    if ievent % 100 == 0:
        print("fetching event: {0} from the database {1} ...".format(
            event_i, database_file))
    eventGroup = h5_data.get(event_i)
    outdata[event_i] = {}
    vn_filename = f"particle_9999_vndata_diff_eta_-0.5_0.5{weakString}.dat"
    vn_data = np.nan_to_num(eventGroup.get(vn_filename))
    dN_vector = calcualte_yield_and_meanpT(0.0, 3.0, vn_data)
    outdata[event_i]["Nch"] = dN_vector[0]
    outdata[event_i]["mean_pT_ch"] = dN_vector[1]

    # compute dET/deta
    vn_filename = f"particle_99999_dNdeta_pT_0_4{weakString}.dat"
    vn_data = np.nan_to_num(eventGroup.get(vn_filename))
    dN_vector = calcualte_inte_Vn_eta(-0.5, 0.5, vn_data, vnFlag=False)
    outdata[event_i]["ET"] = dN_vector[1]

    if initialFlag:
        # initial eccentricity
        ecc_filename = "eccentricities_evo_ed_tau_INITIAL.dat"
        eccn_data = np.nan_to_num(eventGroup.get(ecc_filename))
        outdata[event_i]["ecc_n"] = eccn_data[2:]

    # identified particle yields and mean pT
    for pidName, pid in pidList[1:]:
        vn_filename = f"particle_{pid}_vndata_diff_y_-0.5_0.5{weakString}.dat"
        vn_data = np.nan_to_num(eventGroup.get(vn_filename))
        dN_vector = calcualte_yield_and_meanpT(0.0, 3.0, vn_data)
        outdata[event_i]["{}_dNdy_meanpT".format(pidName)] = dN_vector

    # charged hadron vn with different kinematic cuts
    # try both 9999 and 99999 dataset name conventions
    vn_filename_candidates = [
        f'particle_9999_pTeta_distribution{weakString}.dat',
        f'particle_99999_pTeta_distribution{weakString}.dat'
    ]
    vnInte_filename_candidates = [
        f'particle_9999_vndata_eta_-0.5_0.5{weakString}.dat',
        f'particle_99999_vndata_eta_-0.5_0.5{weakString}.dat'
    ]
    for exp_i, expName in enumerate(kinematicCutsDict):
        pTetacut = kinematicCutsDict[expName]
        vn_data = None
        vnInte_data = None
        for cand in vn_filename_candidates:
            tmp = eventGroup.get(cand)
            if tmp is not None:
                vn_data = np.nan_to_num(tmp)
                break
        for cand in vnInte_filename_candidates:
            tmp = eventGroup.get(cand)
            if tmp is not None:
                vnInte_data = np.nan_to_num(tmp)
                break
        if vn_data is None or vnInte_data is None:
            print(
                f"Warning: missing pT/eta distribution datasets for event {event_i}; skipping {expName}"
            )
            continue
        N_hadronic_events = vnInte_data[-1, 2]
        Vn_vector = calcualte_inte_Vn_pTeta(pTetacut['pTmin'],
                                            pTetacut['pTmax'],
                                            pTetacut['etamin'],
                                            pTetacut['etamax'], vn_data,
                                            N_hadronic_events)
        # store Vn_vector as list to preserve per-order shapes
        outdata[event_i][expName] = Vn_vector

    if pTdiffFlag:
        # pT-differential spectra and vn
        for pidName, pid in pidList:
            if pid == "9999":
                vn_filename = (
                    f"particle_9999_vndata_diff_eta_-0.5_0.5{weakString}.dat")
            else:
                vn_filename = (
                    f"particle_{pid}_vndata_diff_y_-0.5_0.5{weakString}.dat")
            vn_data = np.nan_to_num(eventGroup.get(vn_filename))
            if pid == "9999":
                outdata[event_i]["pTArr"] = vn_data[:, 0]
            pTdiffData = [vn_data[:, 1]]
            for iOrder in range(1, 5):
                pTdiffData.append(vn_data[:, 2*iOrder]
                                  + 1j*vn_data[:, 2*iOrder + 1])
            outdata[event_i][f"{pidName}_pTArr"] = np.array(pTdiffData)

    if photonFlag:
        eventData = get3DGlauberData(eventGroup)
        outdata[event_i]["Ncoll"] = eventData[2]
        outdata[event_i]["Npart"] = eventData[1]
        outdata[event_i]["b"] = eventData[0]

        photonFullres = []
        for ichannel, channelName in enumerate(photonList):
            vn_filename = f"{channelName}_Spvn_tot_ypTdiff.dat"
            raw = eventGroup.get(vn_filename)
            if raw is None:
                print(
                    f"Warning: missing photon dataset {vn_filename} for event {event_i}; skipping channel"
                )
                continue
            vn_data = np.nan_to_num(raw)
            if ichannel == 0 or len(photonFullres) == 0:
                photonFullres = np.array(vn_data, copy=True)
                if photonFullres.size > 0:
                    photonFullres[:, 3:] = (vn_data[:, 3:]
                                            *vn_data[:, 2].reshape(-1, 1))
            else:
                photonFullres[:, 2] += vn_data[:, 2]
                photonFullres[:, 3:] += (vn_data[:, 3:]
                                         *vn_data[:, 2].reshape(-1, 1))
        if len(photonFullres) > 0:
            photonFullres[:, 3:] /= photonFullres[:, 2].reshape(-1, 1)
            outdata[event_i]["photon_ypTdiff"] = photonFullres[:, 2:]
            outdata[event_i]["photon_pTArr"] = np.unique(photonFullres[:, 1])
            outdata[event_i]["photon_yArr"] = np.unique(photonFullres[:, 0])
        else:
            print(
                f"No photon channels found for event {event_i}; skipping photon outputs"
            )

        dileptonFileName = "Dilepton_QGPNLO_Spvn_eq_MInv.dat"
        outdata[event_i]["dilepton_MInv"] = (np.nan_to_num(
            eventGroup.get(dileptonFileName)))
        dileptonFileName = "Dilepton_QGPNLO_Spvn_eq_MInvpTdiff.dat"
        outdata[event_i]["dilepton_MInvpTdiff"] = (np.nan_to_num(
            eventGroup.get(dileptonFileName)))

    if etadiffFlag:
        # eta-differential spectra and vn
        vn_filename_candidates = [
            f'particle_9999_pTeta_distribution{weakString}.dat',
            f'particle_99999_pTeta_distribution{weakString}.dat'
        ]
        vnInte_filename_candidates = [
            f'particle_9999_vndata_eta_-0.5_0.5{weakString}.dat',
            f'particle_99999_vndata_eta_-0.5_0.5{weakString}.dat'
        ]
        vn_data = None
        vnInte_data = None
        for cand in vn_filename_candidates:
            tmp = eventGroup.get(cand)
            if tmp is not None:
                vn_data = np.nan_to_num(tmp)
                break
        for cand in vnInte_filename_candidates:
            tmp = eventGroup.get(cand)
            if tmp is not None:
                vnInte_data = np.nan_to_num(tmp)
                break
        if vn_data is None or vnInte_data is None:
            print(
                f"Warning: missing pT/eta distribution datasets for event {event_i}; skipping eta-differential vn"
            )
        else:
            N_hadronic_events = vnInte_data[-1, 2]
            # for longitudinal derrelation
            Vn_vector = calcualte_inte_Vneta_pTeta(0.4, 4.0, vn_data,
                                                   N_hadronic_events, 0)
            outdata[event_i]["chVneta_pT_0p4_4"] = Vn_vector

            # for vn(eta)
            Vn_vector = calcualte_inte_Vneta_pTeta(0.15, 2.0, vn_data,
                                                   N_hadronic_events, 0)
            outdata[event_i]["chVneta_pT_0p15_2"] = Vn_vector
            Vn_vector = calcualte_inte_Vneta_pTeta(0.15, 2.0, vn_data,
                                                   N_hadronic_events, 1)
            outdata[event_i]["chVneta_pTw_pT_0p15_2"] = Vn_vector

        vn_filename = f"particle_9999_dNdeta_pT_0.2_3{weakString}.dat"
        vn_data = np.nan_to_num(eventGroup.get(vn_filename))
        outdata[event_i]["dNch/deta"] = vn_data[:, 1]

        vn_filename = f"particle_99999_dNdeta_pT_0_4{weakString}.dat"
        vn_data = np.nan_to_num(eventGroup.get(vn_filename))
        outdata[event_i]["dET/deta"] = vn_data[:, -2]
        outdata[event_i]["etaArr"] = vn_data[:, 0]

print("nev = {}".format(len(eventList)))
with open(f'QnVectors{weakString}.pickle', 'wb') as pf:
    pickle.dump(outdata, pf)

h5_data.close()
