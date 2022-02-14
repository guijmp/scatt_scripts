import numpy as np
import mantid
from mantid.simpleapi import *
from scipy import optimize
import time
from pathlib import Path

#######################################################################################################################################
#######################################################                      ##########################################################
#######################################################     USER SECTION     ##########################################################
#######################################################                      ##########################################################
#######################################################################################################################################
'''
The user section is composed of an initialisation section, an iterative analysis/reduction section
of the spectra in the time-of-flight domain, and a final section where the analysis of the corrected
hydrogen neutron Compton profile is possible in the Y-space domain.

The fit procedure in the time-of-flight domain is  based on the scipy.minimize.optimize() tool,
used with the SLSQP minimizer, that can handle both boundaries and constraints for fitting parameters.
'''

start_time = time.time()
# format print output of arrays
np.set_printoptions(suppress=True, precision=4, linewidth=150)
repoPath = Path(__file__).absolute().parent  # Path to the repository


class InitialConditions:
# Parameters for Raw and Empty Workspaces
    name = 'CePtGe12_100K_DD_'
    userWsRawPath = r"./input_ws/CePtGe12_100K_DD_raw.nxs"
    userWsEmptyPath = r"./input_ws/CePtGe12_100K_DD_empty.nxs"

    runs='44462-44463'         # 100K             # The numbers of the runs to be analysed
    empty_runs='43868-43911'   # 100K             # The numbers of the empty runs to be subtracted
    spectra='3-134'                               # Spectra to be analysed
    tof_binning='275.,1.,420'                     # Binning of ToF spectra
    mode='DoubleDifference'
    ipfile='ip2018.par'
    rawAndEmptyWsConfigs = [name, runs, empty_runs, spectra, tof_binning, mode, ipfile]

    # Masses, instrument parameters and initial fitting parameters
    masses = np.array([140.1, 195.1, 72.6, 27]).reshape(4, 1, 1)  #Will change to shape(4, 1) in the future
    noOfMasses = len(masses)
    InstrParsPath = repoPath / "ip2018.par"

    # Elements                                                             Cerium     Platinum     Germanium    Aluminium
    # Classical value of Standard deviation of the momentum distribution:  16.9966    20.0573      12.2352      7.4615         inv A
    # Debye value of Standard deviation of the momentum distribution:      18.22      22.5         15.4         9.93           inv A
    # Intensities Constraints:
    # CePt4Ge12 in Al can                 Cerium                  Platinum                  Germanium
    # Cross section * Stoichiometry:      2.94*1 = 2.94           11.71*4 = 46.84           8.6*12 = 103.2        barn

    initPars = np.array([ 
    # Intensities, NCP widths, NCP centers
        1, 18.22, 0,   # Cerium
        1, 22.5, 0,    # Platinum
        1, 15.4, 0,    # Germanium
        1, 9.93, 0     # Aluminium
    ])
    bounds = np.array([
        [0, np.nan], [17, 20], [-30, 30],
        [0, np.nan], [20, 25], [-30, 30],
        [0, np.nan], [12.2, 18], [-10, 10],
        [0, np.nan], [9.8, 10], [-10, 10]
    ])
    constraints = ({'type': 'eq', 'fun': lambda pars:  pars[0] - 2.94/46.84*pars[3]},
                {'type': 'eq', 'fun': lambda pars:  pars[0] - 2.94/103.2*pars[6]})

    # Masked detectors
    maskedSpecNo = np.array([18,34,42,43,59,60,62,118,119,133])

    # Multiscaterring Correction Parameters
    transmission_guess = 0.98        # Experimental value from VesuvioTransmission
    multiple_scattering_order, number_of_events = 2, 1.e5   
    hydrogen_peak = False                 # Hydrogen multiple scattering
    hydrogen_to_mass0_ratio = 0
    # Hydrogen-to-mass[0] ratio obtaiend from the preliminary fit of forward scattering  0.77/0.02 =38.5
    mulscatPars = [hydrogen_peak, hydrogen_to_mass0_ratio, transmission_guess, multiple_scattering_order, number_of_events]

    # Sample slab parameters
    vertical_width, horizontal_width, thickness = 0.1, 0.1, 0.001  # Expressed in meters
    slabPars = [name, vertical_width, horizontal_width, thickness]

    savePath = repoPath / "tests" / "runs_for_testing" / "compare_with_original" 
    syntheticResultsPath = repoPath / "input_ws" / "synthetic_ncp.nxs"

    scalingFactors = np.ones(initPars.shape)
    
    def __init__(self, initialConditionsDict):
        
        D = initialConditionsDict
        self.noOfMSIterations = D["noOfMSIterations"]
        self.firstSpec = D["firstSpec"]
        self.lastSpec = D["lastSpec"]
        self.userpathInitWsFlag = D["userPathInitWsFlag"]
        self.scaleParsFlag = D["scaleParsFlag"]
        self.fitSyntheticWsFlag = D["fitSyntheticWsFlag"] 
        self.errorsForSyntheticNcpFlag = D["errorsForSyntheticNcpFlag"]

        self.specOffset = self.firstSpec
        self.firstIdx = self.firstSpec - self.specOffset
        self.lastIdx = self.lastSpec - self.specOffset
        self.maskedSpecNo = self.maskedSpecNo[(self.maskedSpecNo >= self.firstSpec) & (self.maskedSpecNo <= self.lastSpec)]
        self.maskedDetectorIdx = self.maskedSpecNo - self.specOffset

    def prepareScalingFactors(self):
        """Returns array used for scaling the fitting parameters.
        Default is parameters not going to be scaled.
        If Boolean Flag is set to True, centers are changed to one (can not be zero),
        and scaling factors normalize the scaling parameters.
        """
        if self.scaleParsFlag:
            self.initPars[2::3] = np.ones((1, self.noOfMasses))  # Can experiment with other starting points
            self.scalingFactors = 1 / self.initPars


initialConditionsDict = {
    "noOfMSIterations" : 1, 
    "firstSpec" : 3, 
    "lastSpec" : 134,
    "userPathInitWsFlag" : True, 
    "scaleParsFlag" : False, 
    "fitSyntheticWsFlag" : False,
    "errorsForSyntheticNcpFlag" : False   # Non-zero dataE when creating NCP workspaces
}


ic = InitialConditions(initialConditionsDict)  


def main():

    wsToBeFittedUncropped = prepareWorkspaceToBeFitted()
    wsToBeFitted = cropAndCloneWorkspace(wsToBeFittedUncropped)
    MaskDetectors(Workspace=wsToBeFitted, WorkspaceIndexList=ic.maskedDetectorIdx)
    ic.prepareScalingFactors()
    createSlabGeometry(ic.slabPars)
    # Initialize arrays to store script results
    thisScriptResults = resultsObject(wsToBeFitted)

    for iteration in range(ic.noOfMSIterations):
        # Workspace from previous iteration
        wsToBeFitted = mtd[ic.name+str(iteration)]

        fittedNcpResults = fitNcpToWorkspace(wsToBeFitted)

        thisScriptResults.append(iteration, fittedNcpResults)
        if (iteration < ic.noOfMSIterations - 1):  # evaluate MS correction except if last iteration
            meanWidths, meanIntensityRatios = fittedNcpResults[:2]

            createWorkspacesForMSCorrection(meanWidths, meanIntensityRatios, ic.mulscatPars)
            Minus(LHSWorkspace=ic.name, RHSWorkspace=ic.name+"_MulScattering",
                  OutputWorkspace=ic.name+str(iteration+1))

    thisScriptResults.save(ic.savePath)


######################################################################################################################################
#####################################################                          #######################################################
#####################################################   DEVELOPMENT SECTION    #######################################################
#####################################################                          #######################################################
######################################################################################################################################
""""
All the functions required to run main() are listed below, in order of appearance
"""

def prepareWorkspaceToBeFitted():
    if ic.fitSyntheticWsFlag:
        wsToBeFitted = loadSyntheticNcpWorkspace()
    else:
        wsToBeFitted = loadVesuvioDataWorkspaces()
    return wsToBeFitted


def loadSyntheticNcpWorkspace():
    """Loads a synthetic ncpTotal workspace from previous fit results path"""
    wsToBeFitted = Load(Filename=str(ic.syntheticResultsPath), OutputWorkspace=ic.name) 
    return wsToBeFitted


def loadVesuvioDataWorkspaces():
    """Loads raw and empty workspaces from either LoadVesuvio or user specified path"""
    if ic.userpathInitWsFlag:
        wsToBeFitted =  loadRawAndEmptyWsFromUserPath()
    else:
        wsToBeFitted = loadRawAndEmptyWsVesuvio()
    return wsToBeFitted


def loadRawAndEmptyWsFromUserPath():
    name, runs, empty_runs, spectra, tof_binning, mode, ipfile = ic.rawAndEmptyWsConfigs

    print('\n', 'Loading the sample runs: ', runs, '\n')
    Load(Filename=ic.userWsRawPath, OutputWorkspace=name+"raw")
    Rebin(InputWorkspace=name+'raw', Params=tof_binning,
          OutputWorkspace=name+'raw')
    SumSpectra(InputWorkspace=name+'raw', OutputWorkspace=name+'raw'+'_sum')

    print('\n', 'Loading the empty runs: ', empty_runs, '\n')
    Load(Filename=ic.userWsEmptyPath, OutputWorkspace=name+"empty")
    Rebin(InputWorkspace=name+'empty', Params=tof_binning,
          OutputWorkspace=name+'empty')
    wsToBeFitted = Minus(LHSWorkspace=name+'raw', RHSWorkspace=name+'empty',
                         OutputWorkspace=name)
    print(wsToBeFitted.name())
    return wsToBeFitted


def loadRawAndEmptyWsVesuvio():
    name, runs, empty_runs, spectra, tof_binning, mode, ipfile = ic.rawAndEmptyWsConfigs
    
    print('\nLoading the sample runs: ', runs, '\n')
    LoadVesuvio(
        Filename=runs, SpectrumList=spectra, Mode=mode, 
        InstrumentParFile=ipfile, OutputWorkspace=name+'raw', LoadLogFiles=False
        )
    Rebin(
        InputWorkspace=name+'raw', Params=tof_binning, OutputWorkspace=name+'raw'
        )
    SumSpectra(InputWorkspace=name+'raw', OutputWorkspace=name+'raw'+'_sum')

    print('\n', 'Loading the empty runs: ', empty_runs, '\n')
    LoadVesuvio(
        Filename=empty_runs, SpectrumList=spectra, Mode=mode,
        InstrumentParFile=ipfile, OutputWorkspace=name+'empty', LoadLogFiles=False
        )
    Rebin(
        InputWorkspace=name+'empty', Params=tof_binning, OutputWorkspace=name+'empty'
        )
          
    wsToBeFitted = Minus(
        LHSWorkspace=name+'raw', RHSWorkspace=name+'empty', OutputWorkspace=name
        )
    return wsToBeFitted


def cropAndCloneWorkspace(ws):
    """Returns cloned and cropped workspace with modified name"""
    CropWorkspace(InputWorkspace=ws, StartWorkspaceIndex=ic.firstIdx,
                  EndWorkspaceIndex=ic.lastIdx, OutputWorkspace=ws.name())
    wsToBeFitted = CloneWorkspace(
        InputWorkspace=ws.name(), OutputWorkspace=ws.name()+"0")
    return wsToBeFitted


def createSlabGeometry(slabPars):
    name, vertical_width, horizontal_width, thickness = slabPars
    half_height, half_width, half_thick = 0.5*vertical_width, 0.5*horizontal_width, 0.5*thickness
    xml_str = \
        " <cuboid id=\"sample-shape\"> " \
        + "<left-front-bottom-point x=\"%f\" y=\"%f\" z=\"%f\" /> " % (half_width, -half_height, half_thick) \
        + "<left-front-top-point x=\"%f\" y=\"%f\" z=\"%f\" /> " % (half_width, half_height, half_thick) \
        + "<left-back-bottom-point x=\"%f\" y=\"%f\" z=\"%f\" /> " % (half_width, -half_height, -half_thick) \
        + "<right-front-bottom-point x=\"%f\" y=\"%f\" z=\"%f\" /> " % (-half_width, -half_height, half_thick) \
        + "</cuboid>"
    CreateSampleShape(name, xml_str)


class resultsObject:
    """Used to store results of the script"""

    def __init__(self, wsToBeFitted):
        """Initializes arrays full of zeros"""

        noOfSpec = wsToBeFitted.getNumberHistograms()
        lenOfSpec = wsToBeFitted.blocksize()

        all_fit_workspaces = np.zeros((ic.noOfMSIterations, noOfSpec, lenOfSpec))
        all_spec_best_par_chi_nit = np.zeros(
            (ic.noOfMSIterations, noOfSpec, ic.noOfMasses*3+3))
        all_tot_ncp = np.zeros((ic.noOfMSIterations, noOfSpec, lenOfSpec - 1))
        all_mean_widths = np.zeros((ic.noOfMSIterations, ic.noOfMasses))
        all_mean_intensities = np.zeros(all_mean_widths.shape)

        resultsList = [all_mean_widths, all_mean_intensities,
                       all_spec_best_par_chi_nit, all_tot_ncp, all_fit_workspaces]
        self.resultsList = resultsList

    def append(self, mulscatIter, resultsToAppend):
        """Append results at a given MS iteration"""
        for i, currentMSArray in enumerate(resultsToAppend):
            self.resultsList[i][mulscatIter] = currentMSArray

    def save(self, savePath):
        all_mean_widths, all_mean_intensities, all_spec_best_par_chi_nit, all_tot_ncp, all_fit_workspaces = self.resultsList
        np.savez(savePath,
                 all_fit_workspaces=all_fit_workspaces,
                 all_spec_best_par_chi_nit=all_spec_best_par_chi_nit,
                 all_mean_widths=all_mean_widths,
                 all_mean_intensities=all_mean_intensities,
                 all_tot_ncp=all_tot_ncp)


def fitNcpToWorkspace(ws):
    """Firstly calculates matrices for all spectrums,
    then iterates over each spectrum
    """
    wsDataY = ws.extractY()       #DataY unaltered
    dataY, dataX, dataE = loadWorkspaceIntoArrays(ws)                     
    resolutionPars, instrPars, kinematicArrays, ySpacesForEachMass = prepareFitArgs(dataX)
    
    #-------------Fit all spectrums----------
    fitPars = np.array(list(map(
        fitNcpToSingleSpec, 
        dataY, dataE, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays
    )))
    fitParsObj = fitParameters(fitPars)
    fitParsObj.printPars()
    meanWidths, meanIntensityRatios = fitParsObj.getMeanWidthsAndIntensities()

    # Create ncpTotal workspaces
    mainPars = fitParsObj.mainPars
    ncpForEachMass = np.array(list(map(
        buildNcpFromSpec, 
        mainPars , ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays
    )))
    ncpTotal = np.sum(ncpForEachMass, axis=1)  
    createNcpWorkspaces(ncpForEachMass, ncpTotal, ws)  

    return [meanWidths, meanIntensityRatios, fitPars, ncpTotal, wsDataY]


def loadWorkspaceIntoArrays(ws):
    """Output: dataY, dataX and dataE as arrays and converted to point data"""
    dataY = ws.extractY()
    dataE = ws.extractE()
    dataX = ws.extractX()

    histWidths = dataX[:, 1:] - dataX[:, :-1]
    dataY = dataY[:, :-1] / histWidths
    dataE = dataE[:, :-1] / histWidths
    dataX = (dataX[:, 1:] + dataX[:, :-1]) / 2
    return dataY, dataX, dataE


def prepareFitArgs(dataX):
    instrPars = loadInstrParsFileIntoArray(ic.InstrParsPath, ic.firstSpec, ic.lastSpec)        #shape(134,-)
    resolutionPars = loadResolutionPars(instrPars)                           #shape(134,-)        

    v0, E0, delta_E, delta_Q = calculateKinematicsArrays(dataX, instrPars)   #shape(134, 144)
    kinematicArrays = np.array([v0, E0, delta_E, delta_Q])
    ySpacesForEachMass = convertDataXToYSpacesForEachMass(dataX, ic.masses, delta_Q, delta_E)        #shape(134, 4, 144)
    
    kinematicArrays = reshapeArrayPerSpectrum(kinematicArrays)
    ySpacesForEachMass = reshapeArrayPerSpectrum(ySpacesForEachMass)
    return resolutionPars, instrPars, kinematicArrays, ySpacesForEachMass


def loadInstrParsFileIntoArray(InstrParsPath, firstSpec, lastSpec):
    """Loads instrument parameters into array, from the file in the specified path"""
    data = np.loadtxt(InstrParsPath, dtype=str)[1:].astype(float)

    spectra = data[:, 0]
    select_rows = np.where((spectra >= firstSpec) & (spectra <= lastSpec))
    instrPars = data[select_rows]
    print("instrPars first column: \n", instrPars[:, 0])  
    return instrPars


def loadResolutionPars(instrPars):
    """Resolution of parameters to propagate into TOF resolution
       Output: matrix with each parameter in each column"""
    spectrums = instrPars[:, 0] 
    L = len(spectrums)
    #for spec no below 135, back scattering detectors, in case of double difference
    #for spec no 135 or above, front scattering detectors, in case of single difference
    dE1 = np.where(spectrums < 135, 88.7, 73)   #meV, STD
    dE1_lorz = np.where(spectrums < 135, 40.3, 24)  #meV, HFHM
    dTOF = np.repeat(0.37, L)      #us
    dTheta = np.repeat(0.016, L)   #rad
    dL0 = np.repeat(0.021, L)      #meters
    dL1 = np.repeat(0.023, L)      #meters
    
    resolutionPars = np.vstack((dE1, dTOF, dTheta, dL0, dL1, dE1_lorz)).transpose()  #store all parameters in a matrix
    return resolutionPars 

def calculateKinematicsArrays(dataX, instrPars):          
    """Kinematics quantities calculated from TOF data"""   
    mN, Ef, en_to_vel, vf, hbar = loadConstants()    
    det, plick, angle, T0, L0, L1 = np.hsplit(instrPars, 6)     #each is of len(dataX)
    t_us = dataX - T0                                         #T0 is electronic delay due to instruments
    v0 = vf * L0 / ( vf * t_us - L1 )
    E0 =  np.square( v0 / en_to_vel )            #en_to_vel is a factor used to easily change velocity to energy and vice-versa
    
    delta_E = E0 - Ef  
    delta_Q2 = 2. * mN / hbar**2 * ( E0 + Ef - 2. * np.sqrt(E0*Ef) * np.cos(angle/180.*np.pi) )
    delta_Q = np.sqrt( delta_Q2 )
    return v0, E0, delta_E, delta_Q              #shape(no_spectrums, len_spec)

def reshapeArrayPerSpectrum(A):
    """Exchanges the first two indices of an array A,
    ao rearranges array to match iteration per spectrum of main fitting map()
    """
    return np.stack(np.split(A, len(A), axis=0), axis=2)[0]

def convertDataXToYSpacesForEachMass(dataX, masses, delta_Q, delta_E):
    "Calculates y spaces from TOF data, each row corresponds to one mass"   
    dataX, delta_Q, delta_E = dataX[np.newaxis, :, :],  delta_Q[np.newaxis, :, :], delta_E[np.newaxis, :, :]   #prepare arrays to broadcast
    mN, Ef, en_to_vel, vf, hbar = loadConstants()
    noOfMasses = len(masses)
    masses = masses.reshape(noOfMasses, 1, 1)

    energyRecoil = np.square( hbar * delta_Q ) / 2. / masses              
    ySpacesForEachMass = masses / hbar**2 /delta_Q * (delta_E - energyRecoil)    #y-scaling  
    return ySpacesForEachMass

def fitNcpToSingleSpec(dataY, dataE, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays):
    """Fits the NCP and returns the best fit parameters for one spectrum"""

    if np.all(dataY == 0) | np.all(np.isnan(dataY)): 
        return np.full(len(ic.initPars)+3, np.nan)
    
    scaledPars = ic.initPars * ic.scalingFactors
    scaledBounds = ic.bounds * ic.scalingFactors[:, np.newaxis]

    result = optimize.minimize(
        errorFunction, 
        scaledPars, 
        args=(ic.masses, dataY, dataE, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays),
        method='SLSQP', 
        bounds = scaledBounds, 
        constraints=ic.constraints
        )

    fitScaledPars = result["x"]
    fitPars = fitScaledPars / ic.scalingFactors

    noDegreesOfFreedom = len(dataY) - len(fitPars)
    specFitPars = np.append(instrPars[0], fitPars)
    return np.append(specFitPars, [result["fun"] / noDegreesOfFreedom, result["nit"]])


def errorFunction(scaledPars, masses, dataY, dataE, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays):
    """Error function to be minimized, operates in TOF space"""

    unscaledPars = scaledPars / ic.scalingFactors
    ncpForEachMass, ncpTotal = calculateNcpSpec(unscaledPars, masses, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays)

    if np.all(dataE == 0) | np.all(np.isnan(dataE)):
        # This condition is not usually satisfied but in the exceptional case that it is,
        # we can use a statistical weight to make sure the chi2 used is not too small for the 
        # optimization algorithm
        chi2 = (ncpTotal - dataY)**2 / dataY**2
    else:
        chi2 =  (ncpTotal - dataY)**2 / dataE**2    
    return np.sum(chi2)


def calculateNcpSpec(unscaledPars, masses, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays):    
    """Creates a synthetic C(t) to be fitted to TOF values, from J(y) and resolution functions
       shapes: initPars (1, 12), masses (4,1,1), datax (1, n), ySpacesForEachMass (4, n), res (4, 2), deltaQ (1, n), E0 (1,n)"""
    
    masses, intensities, widths, centers = prepareArraysFromPars(masses, unscaledPars) 
    v0, E0, deltaE, deltaQ = kinematicArrays
    
    gaussRes, lorzRes = caculateResolutionForEachMass(
        masses, ySpacesForEachMass, centers, resolutionPars, instrPars, kinematicArrays
        )
    totalGaussWidth = np.sqrt(widths**2 + gaussRes**2)                 
    
    JOfY = pseudoVoigt(ySpacesForEachMass - centers, totalGaussWidth, lorzRes)  
    
    FSE =  - numericalThirdDerivative(ySpacesForEachMass, JOfY) * widths**4 / deltaQ * 0.72 
    
    ncpForEachMass = intensities * (JOfY + FSE) * E0 * E0**(-0.92) * masses / deltaQ   
    ncpTotal = np.sum(ncpForEachMass, axis=0)
    return ncpForEachMass, ncpTotal


def prepareArraysFromPars(masses, initPars):
    noOfMasses = len(masses)
    shapeOfArrays = (noOfMasses, 1)
    masses = masses.reshape(shapeOfArrays)    
    intensities = initPars[::3].reshape(shapeOfArrays)
    widths = initPars[1::3].reshape(shapeOfArrays)
    centers = initPars[2::3].reshape(shapeOfArrays)  
    return masses, intensities, widths, centers 


def caculateResolutionForEachMass(masses, ySpacesForEachMass, centers, resolutionPars, instrPars, kinematicArrays):    
    """Calculates the gaussian and lorentzian resolution
    output: two column vectors, each row corresponds to each mass"""
    
    v0, E0, delta_E, delta_Q = kinematicsAtYCenters(ySpacesForEachMass, centers, kinematicArrays)
    
    gaussianResWidth = calcGaussianResolution(masses, v0, E0, delta_E, delta_Q, resolutionPars, instrPars)
    lorentzianResWidth = calcLorentzianResolution(masses, v0, E0, delta_E, delta_Q, resolutionPars, instrPars)
    return gaussianResWidth, lorentzianResWidth


def kinematicsAtYCenters(ySpacesForEachMass, centers, kinematicArrays):
    """v0, E0, deltaE, deltaQ at the center of the ncpTotal for each mass"""
    noOfMasses = len(ySpacesForEachMass)
    shapeOfArrays = (noOfMasses, 1)

    proximityToYCenters = np.abs(ySpacesForEachMass - centers)
    yClosestToCenters = proximityToYCenters.min(axis=1).reshape(shapeOfArrays)
    yCentersMask = proximityToYCenters == yClosestToCenters

    v0, E0, deltaE, deltaQ = kinematicArrays

    # Expand arrays to match shape of yCentersMask
    v0 = v0 * np.ones(shapeOfArrays)
    E0 = E0 * np.ones(shapeOfArrays)
    deltaE = deltaE * np.ones(shapeOfArrays)
    deltaQ = deltaQ * np.ones(shapeOfArrays)

    v0 = v0[yCentersMask].reshape(shapeOfArrays)
    E0 = E0[yCentersMask].reshape(shapeOfArrays)
    deltaE = deltaE[yCentersMask].reshape(shapeOfArrays)
    deltaQ = deltaQ[yCentersMask].reshape(shapeOfArrays)

    # # Could also do it like this, but it's probably slower
    # def selectValuesAtYCenter(kineArray):
    #     kineArray = kineArray * np.ones(shapeOfArrays)
    #     return kineArray[yCentersMask].reshape(shapeOfArrays)
    # v0, E0, deltaE, deltaQ = [selectValuesAtYCenter(A) for A in (v0, E0, deltaE, deltaQ)]
    return v0, E0, deltaE, deltaQ


def calcGaussianResolution(masses, v0, E0, delta_E, delta_Q, resolutionPars, instrPars):
    """Currently the function that takes the most time in the fitting"""

    det, plick, angle, T0, L0, L1 = instrPars
    dE1, dTOF, dTheta, dL0, dL1, dE1_lorz = resolutionPars
    mN, Ef, en_to_vel, vf, hbar = loadConstants()

    angle = angle * np.pi/180

    dWdE1 = 1. + (E0 / Ef)**1.5 * (L1 / L0)
    dWdTOF = 2. * E0 * v0 / L0
    dWdL1 = 2. * E0**1.5 / Ef**0.5 / L0
    dWdL0 = 2. * E0 / L0

    dW2 = dWdE1**2*dE1**2 + dWdTOF**2*dTOF**2 + dWdL1**2*dL1**2 + dWdL0**2*dL0**2
    # conversion from meV^2 to A^-2, dydW = (M/q)^2
    dW2 *= (masses / hbar**2 / delta_Q)**2

    dQdE1 = 1. - (E0 / Ef)**1.5 * L1/L0 - np.cos(angle) * ((E0 / Ef)**0.5 - L1/L0 * E0/Ef)
    dQdTOF = 2.*E0 * v0/L0
    dQdL1 = 2.*E0**1.5 / L0 / Ef**0.5
    dQdL0 = 2.*E0 / L0
    dQdTheta = 2. * np.sqrt(E0 * Ef) * np.sin(angle)

    dQ2 = dQdE1**2*dE1**2 + (dQdTOF**2*dTOF**2 + dQdL1**2*dL1**2 + dQdL0 **
                             2*dL0**2)*np.abs(Ef/E0*np.cos(angle)-1) + dQdTheta**2*dTheta**2
    dQ2 *= (mN / hbar**2 / delta_Q)**2

    # in A-1    #same as dy^2 = (dy/dw)^2*dw^2 + (dy/dq)^2*dq^2
    gaussianResWidth = np.sqrt(dW2 + dQ2)
    return gaussianResWidth


def calcLorentzianResolution(masses, v0, E0, delta_E, delta_Q, resolutionPars, instrPars):
    det, plick, angle, T0, L0, L1 = instrPars
    dE1, dTOF, dTheta, dL0, dL1, dE1_lorz = resolutionPars
    mN, Ef, en_to_vel, vf, hbar = loadConstants()

    angle = angle * np.pi / 180

    dWdE1_lor = (1. + (E0/Ef)**1.5 * (L1/L0))**2
    # conversion from meV^2 to A^-2
    dWdE1_lor *= (masses / hbar**2 / delta_Q)**2

    dQdE1_lor = (1. - (E0/Ef)**1.5 * L1/L0 - np.cos(angle)
                 * ((E0/Ef)**0.5 + L1/L0 * E0/Ef))**2
    dQdE1_lor *= (mN / hbar**2 / delta_Q)**2

    lorentzianResWidth = np.sqrt(dWdE1_lor + dQdE1_lor) * dE1_lorz   # in A-1
    return lorentzianResWidth


def loadConstants():
    """Output: the mass of the neutron, final energy of neutrons (selected by gold foil),
    factor to change energies into velocities, final velocity of neutron and hbar"""
    mN=1.008    #a.m.u.
    Ef=4906.         # meV
    en_to_vel = 4.3737 * 1.e-4
    vf = np.sqrt(Ef) * en_to_vel  # m/us
    hbar = 2.0445
    return mN, Ef, en_to_vel, vf, hbar


def pseudoVoigt(x, sigma, gamma):
    """Convolution between Gaussian with std sigma and Lorentzian with HWHM gamma"""
    fg, fl = 2.*sigma*np.sqrt(2.*np.log(2.)), 2.*gamma
    f = 0.5346 * fl + np.sqrt(0.2166*fl**2 + fg**2)
    eta = 1.36603 * fl/f - 0.47719 * (fl/f)**2 + 0.11116 * (fl/f)**3
    sigma_v, gamma_v = f/(2.*np.sqrt(2.*np.log(2.))), f / 2.
    pseudo_voigt = eta * \
        lorentizian(x, gamma_v) + (1.-eta) * gaussian(x, sigma_v)
    norm = np.sum(pseudo_voigt)*(x[1]-x[0])
    return pseudo_voigt  # /np.abs(norm)


def gaussian(x, sigma):
    """Gaussian function centered at zero"""
    gaussian = np.exp(-x**2/2/sigma**2)
    gaussian /= np.sqrt(2.*np.pi)*sigma
    return gaussian


def lorentizian(x, gamma):
    """Lorentzian centered at zero"""
    lorentzian = gamma/np.pi / (x**2 + gamma**2)
    return lorentzian


def numericalThirdDerivative(x, fun):
    k6 = (- fun[:, 12:] + fun[:, :-12]) * 1
    k5 = (+ fun[:, 11:-1] - fun[:, 1:-11]) * 24
    k4 = (- fun[:, 10:-2] + fun[:, 2:-10]) * 192
    k3 = (+ fun[:,  9:-3] - fun[:, 3:-9]) * 488
    k2 = (+ fun[:,  8:-4] - fun[:, 4:-8]) * 387
    k1 = (- fun[:,  7:-5] + fun[:, 5:-7]) * 1584

    dev = k1 + k2 + k3 + k4 + k5 + k6
    dev /= np.power(x[:, 7:-5] - x[:, 6:-6], 3)
    dev /= 12**3

    derivative = np.zeros(fun.shape)
    # need to pad with zeros left and right to return array with same shape
    derivative[:, 6:-6] = dev
    return derivative


class fitParameters:
    """Stores the fitted parameters from map and defines methods to extract information"""

    def __init__(self, fitPars):
        self.spec = fitPars[:, 0][:, np.newaxis]
        self.chi2 = fitPars[:, -2][:, np.newaxis]
        self.nit = fitPars[:, -1][:, np.newaxis]

        mainPars = fitPars[:, 1:-2]
        self.intensities = mainPars[:, 0::3]
        self.widths = mainPars[:, 1::3]
        self.centers = mainPars[:, 2::3]
        self.mainPars = mainPars

    def printPars(self):
        print("[Spec Intensities----Widths----Centers Chi2 Nit]:\n\n", 
              np.hstack((self.spec, self.intensities, self.widths, self.centers, self.chi2, self.nit)))

    def getMeanWidthsAndIntensities(self):
        noOfMasses = ic.noOfMasses
        widths = self.widths.T
        intensities = self.intensities.T

        meanWidths = np.nanmean(widths, axis=1).reshape(noOfMasses, 1)  
        stdWidths = np.nanstd(widths, axis=1).reshape(noOfMasses, 1)

        # Subtraction row by row
        widthDeviation = np.abs(widths - meanWidths)
        # Where True, replace by nan
        betterWidths = np.where(widthDeviation > stdWidths, np.nan, widths)
        betterIntensities = np.where(widthDeviation > stdWidths, np.nan, intensities)

        meanWidths = np.nanmean(betterWidths, axis=1)  
        stdWidths = np.nanstd(betterWidths, axis=1)

        # Not nansum(), to propagate nan
        normalization = np.sum(betterIntensities, axis=0)
        intensityRatios = betterIntensities / normalization

        meanIntensityRatios = np.nanmean(intensityRatios, axis=1)
        stdIntensityRatios = np.nanstd(intensityRatios, axis=1)

        print("\nMasses: ", ic.masses.reshape(1, 4),
            "\nMean Widths: ", meanWidths,
            "\nMean Intensity Ratios: ", meanIntensityRatios)
        return meanWidths, meanIntensityRatios


def buildNcpFromSpec(initPars, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays):
    """input: all row shape
       output: row shape with the ncpTotal for each mass"""

    if np.all(np.isnan(initPars)):
        return np.full(ySpacesForEachMass.shape, np.nan)
    
    ncpForEachMass, ncpTotal = calculateNcpSpec(initPars, ic.masses, ySpacesForEachMass, resolutionPars, instrPars, kinematicArrays)        
    return ncpForEachMass


def createNcpWorkspaces(ncpForEachMass, ncpTotal, ws):
    """Creates workspaces from ncp array data"""

    # Need to rearrage array of yspaces into seperate arrays for each mass
    ncpForEachMass = switchFirstTwoAxis(ncpForEachMass)
    dataX = ws.extractX()
    dataE = np.zeros(dataX.shape)

    if ic.errorsForSyntheticNcpFlag:   # Generates synthetic ncp data with homoscedastic error bars
        wsDataE = ws.extractE()
        dataE = np.mean(wsDataE, axis=1)[:, np.newaxis] * np.ones((1, len(dataX[0])))

    # Not sure this is correct
    histWidths = dataX[:, 1:] - dataX[:, :-1]
    dataX = dataX[:, :-1]  # Cut last column to match ncpTotal length
    dataY = ncpTotal * histWidths
    dataE = dataE[:, :-1] * histWidths

    CreateWorkspace(DataX=dataX.flatten(), DataY=dataY.flatten(), DataE=dataE.flatten(),
                     Nspec=len(dataX), OutputWorkspace=ws.name()+"_tof_fitted_profiles")

    for i, ncp_m in enumerate(ncpForEachMass):
        CreateWorkspace(DataX=dataX.flatten(), DataY=ncp_m.flatten(), Nspec=len(dataX),
                        OutputWorkspace=ws.name()+"_tof_fitted_profile_"+str(i+1))


def switchFirstTwoAxis(A):
    """Exchanges the first two indices of an array A,
    rearranges matrices per spectrum for iteration of main fitting procedure
    """
    return np.stack(np.split(A, len(A), axis=0), axis=2)[0]


def createWorkspacesForMSCorrection(meanWidths, meanIntensityRatios, mulscatPars):
    """Creates _MulScattering and _TotScattering workspaces used for the MS correction"""
    sample_properties = calculateSampleProperties(
        ic.masses, meanWidths, meanIntensityRatios, "MultipleScattering", mulscatPars)
    createMulScatWorkspaces(ic.name, sample_properties, mulscatPars)


def calculateSampleProperties(masses, meanWidths, meanIntensityRatios, mode, mulscatPars):
    """returns the one of the inputs necessary for the VesuvioCalculateGammaBackground
    or VesuvioCalculateMS"""
    masses = masses.reshape(4)
    hydrogen_peak, hydrogen_to_mass0_ratio = mulscatPars[:2]

    if mode == "GammaBackground":  # Not used for backscattering
        profiles = ""
        for m, mass in enumerate(masses):
            width, intensity = str(meanWidths[m]), str(meanIntensityRatios[m])
            profiles += "name=GaussianComptonProfile,Mass=" + \
                str(mass)+",Width="+width + \
                ",intensities="+intensity+';'
        sample_properties = profiles

    elif mode == "MultipleScattering":
        if hydrogen_peak:
            # ADDITION OF THE HYDROGEN intensities AS PROPORTIONAL TO A FITTED NCP (OXYGEN HERE)
            masses = np.append(masses, 1.0079)
            meanWidths = np.append(meanWidths, 5.0)
            meanIntensityRatios = np.append(
                meanIntensityRatios, hydrogen_to_mass0_ratio * meanIntensityRatios[0])
            meanIntensityRatios /= np.sum(meanIntensityRatios)

        MS_properties = np.zeros(3*len(masses))
        MS_properties[::3] = masses
        MS_properties[1::3] = meanIntensityRatios
        MS_properties[2::3] = meanWidths
        sample_properties = list(MS_properties)
    else:
        print("\n Mode entered not valid")
    print("\n The sample properties for ", mode, " are: ", sample_properties)
    return sample_properties


def createMulScatWorkspaces(ws_name, sample_properties, mulscatPars):
    """Uses the Mantid algorithm for the MS correction to create two Workspaces _TotScattering and _MulScattering"""

    print("Evaluating the Multiple Scattering Correction.")
    transmission_guess, multiple_scattering_order, number_of_events = mulscatPars[2:]
    # selects only the masses, every 3 numbers
    MS_masses = sample_properties[::3]
    # same as above, but starts at first intensities
    MS_amplitudes = sample_properties[1::3]

    dens, trans = VesuvioThickness(
        Masses=MS_masses, Amplitudes=MS_amplitudes, TransmissionGuess=transmission_guess, Thickness=0.1)

    _TotScattering, _MulScattering = VesuvioCalculateMS(
        ws_name, NoOfMasses=len(MS_masses), SampleDensity=dens.cell(9, 1),
        AtomicProperties=sample_properties, BeamRadius=2.5,
        NumScatters=multiple_scattering_order,
        NumEventsPerRun=int(number_of_events))

    data_normalisation = Integration(ws_name)
    simulation_normalisation = Integration("_TotScattering")
    for workspace in ("_MulScattering", "_TotScattering"):
        Divide(LHSWorkspace=workspace,
               RHSWorkspace=simulation_normalisation, OutputWorkspace=workspace)
        Multiply(LHSWorkspace=workspace,
                 RHSWorkspace=data_normalisation, OutputWorkspace=workspace)
        RenameWorkspace(InputWorkspace=workspace,
                        OutputWorkspace=str(ws_name)+workspace)
    DeleteWorkspaces(
        [data_normalisation, simulation_normalisation, trans, dens])
  # The only remaining workspaces are the _MulScattering and _TotScattering


# -------------- Other functions not used yet on main()--------------


# I tested this function but not throughouly, so could have missed something
def subtractAllMassesExceptFirst(ws, ncpForEachMass):
    """Input: workspace from last iteration, ncpTotal for each mass
       Output: workspace with all the ncpTotal subtracted except for the first mass"""

    # Select all masses other than the first one
    ncpForEachMass = ncpForEachMass[1:, :, :]
    # Sum the ncpTotal for remaining masses
    ncpTotal = np.sum(ncpForEachMass, axis=0)
    dataY, dataX, dataE = ws.extractY(), ws.extractX(), ws.extractE()

    # The original uses data_x, ie the mean points of the histograms, not dataX!
    dataY[:, :-1] -= ncpTotal * (dataX[:, 1:] - dataX[:, :-1])
    # But this makes more sense to calculate histogram widths, we can preserve one more data point
    first_ws = CreateWorkspace(DataX=dataX.flatten(), DataY=dataY.flatten(), DataE=dataE.flatten(), Nspec=len(dataX))
    return first_ws


def convertWsToYSpaceAndSymetrise(ws_name, mass):
    """input: TOF workspace
       output: workspace in y-space for given mass with dataY symetrised"""

    ws_y, ws_q = ConvertToYSpace(InputWorkspace=ws_name, Mass=mass,
                                 OutputWorkspace=ws_name+"_JoY", QWorkspace=ws_name+"_Q")
    max_Y = np.ceil(2.5*mass+27)  
    # First bin boundary, width, last bin boundary, 120 bins over range
    rebin_parameters = str(-max_Y)+","+str(2.*max_Y/120)+","+str(max_Y)
    ws_y = Rebin(InputWorkspace=ws_y, Params=rebin_parameters,
                 FullBinsOnly=True, OutputWorkspace=ws_name+"_JoY")

    matrix_Y = ws_y.extractY()
    # safeguarding against nans as well
    matrix_Y[(matrix_Y != 0) & (matrix_Y != np.nan)] = 1
    no_y = np.nansum(matrix_Y, axis=0)

    ws_y = SumSpectra(InputWorkspace=ws_y, OutputWorkspace=ws_name+"_JoY")
    tmp = CloneWorkspace(InputWorkspace=ws_y)
    tmp.dataY(0)[:] = no_y
    tmp.dataE(0)[:] = np.zeros(tmp.blocksize())

    # use of Divide and not nanmean, err are prop automatically
    ws = Divide(LHSWorkspace=ws_y, RHSWorkspace=tmp,
                OutputWorkspace=ws_name+"_JoY")
    ws.dataY(0)[:] = (ws.readY(0)[:] + np.flip(ws.readY(0)[:])) / 2 
    ws.dataE(0)[:] = (ws.readE(0)[:] + np.flip(ws.readE(0)[:])) / 2 
    normalise_workspace(ws)
    return max_Y


def calculate_mantid_resolutions(ws_name, mass):
    # Only for loop in this script because the fuction VesuvioResolution takes in one spectra at a time
    # Haven't really tested this one becuase it's not modified
    max_Y = np.ceil(2.5*mass+27)
    rebin_parameters = str(-max_Y)+","+str(2.*max_Y/240)+","+str(max_Y)
    ws = mtd[ws_name]
    for index in range(ws.getNumberHistograms()):
        VesuvioResolution(Workspace=ws, WorkspaceIndex=index,
                          Mass=mass, OutputWorkspaceySpacesForEachMass="tmp")
        tmp = Rebin("tmp", rebin_parameters)
        if index == 0:
            RenameWorkspace("tmp", "resolution")
        else:
            AppendSpectra("resolution", "tmp", OutputWorkspace="resolution")
    SumSpectra(InputWorkspace="resolution", OutputWorkspace="resolution")
    normalise_workspace("resolution")
    DeleteWorkspace("tmp")


def normalise_workspace(ws_name):
    tmp_norm = Integration(ws_name)
    Divide(LHSWorkspace=ws_name, RHSWorkspace="tmp_norm", OutputWorkspace=ws_name)
    DeleteWorkspace("tmp_norm")

main()
end_time = time.time()
print("running time: ", end_time-start_time, " seconds")