
import numpy as np
import matplotlib .pyplot as plt
from pathlib import Path
from vesuvio_analysis.core_functions.analysis_functions import calculateMeansAndStds, filterWidthsAndIntensities
currentPath = Path(__file__).parent.absolute() 
experimentsPath = currentPath / "experiments"


def calcBootMeans(bestPars):
    """Performs the means and std on each bootstrap sample"""
    bootWidths = bestPars[:, :, 1::3]
    bootIntensities = bestPars[:, :, 0::3]

    bootMeanW = np.zeros((len(bootWidths[0,0,:]), len(bootWidths)))
    bootStdW = np.zeros(bootMeanW.shape)
    bootMeanI = np.zeros(bootMeanW.shape)
    bootStdI = np.zeros(bootMeanW.shape)

    for j, (widths, intensities) in enumerate(zip(bootWidths, bootIntensities)):

        meanW, stdW, meanI, stdI = calculateMeansAndStds(widths.T, intensities.T)

        bootMeanW[:, j] = meanW
        bootStdW[:, j] = stdW
        bootMeanI[:, j] = meanI
        bootStdI[:, j] = stdI

    return bootMeanW, bootMeanI, bootStdW, bootStdI


def plotHists(ax, samples, nBins, title):
    ax.set_title(f"Histogram of {title}")
    for i, bootHist in enumerate(samples):
        leg = f"Row {i}: {np.mean(bootHist):>6.3f} \u00B1 {np.std(bootHist):<6.3f}"
        ax.hist(bootHist, nBins, histtype="step", label=leg)

        ax.axvline(np.mean(bootHist), 0, 0.97, color="k", ls="--")

    ax.legend()


def checkBootSamplesVSParent(bestPars, parentPars):
    """
    For an unbiased estimator, the mean of the bootstrap samples will converge to 
    the mean of the experimental sample (here called parent).
    """

    bootWidths = bestPars[:, :, 1::3]
    bootIntensities = bestPars[:, :, 0::3]

    # TODO: Need to decide on wether to use mean, median or mode
    meanBootWidths = np.median(bootWidths, axis=0)
    meanBootIntensities = np.median(bootIntensities, axis=0)

    avgWidths, stdWidths, avgInt, stdInt = calculateMeansAndStds(meanBootWidths.T, meanBootIntensities.T)

    parentWidths = parentPars[:, 1::3]
    parentIntensities = parentPars[:, 0::3]

    avgWidthsP, stdWidthsP, avgIntP, stdIntP = calculateMeansAndStds(parentWidths.T, parentIntensities.T)
  
    print("\nComparing Bootstrap means with parent means:\n")
    printResults(avgWidths, stdWidths, "Boot Widths")
    printResults(avgWidthsP, stdWidthsP, "Parent Widths")
    printResults(avgInt, stdInt, "Boot Intensities")
    printResults(avgIntP, stdIntP, "Parent Intensities")
    

def plot2DHists(bootSamples, nBins, mode):
    """bootSamples has histogram rows for each parameter"""

    plotSize = len(bootSamples)
    fig, axs = plt.subplots(plotSize, plotSize, figsize=(8, 8))

    for i in range(plotSize):
        for j in range(plotSize):
            if j>i:
                axs[i, j].set_visible(False)

            elif i==j:
                if i>0:
                    orientation="horizontal"
                else:
                    orientation="vertical"

                axs[i, j].hist(bootSamples[i], nBins, orientation=orientation)

            else:
                axs[i, j].hist2d(bootSamples[j], bootSamples[i], nBins)
                
            if j==0:
                axs[i, j].set_ylabel(f"idx {i}")   
            if i==plotSize-1:
                axs[i, j].set_xlabel(f"idx{j}")
    
    fig.suptitle(f"1D and 2D Histograms of {mode}")
    plt.show()


def addParentMeans(ax, means):
    for mean in means:
        ax.axvline(mean, 0, 0.97, color="k", ls=":")
        

def printResults(arrM, arrE, mode):
    print(f"\n{mode}:\n")
    for i, (m, e) in enumerate(zip(arrM, arrE)):
        print(f"{mode} {i}: {m:>6.3f} \u00B1 {e:<6.3f}")


def dataPaths(sampleName, firstSpec, lastSpec, msIter, MS, GC, nSamples, speed):
    # Build Filename based on ic
    corr = ""
    if MS & (msIter>1):
        corr+="_MS"
    if GC & (msIter>1):
        corr+="_GC"

    fileName = f"spec_{firstSpec}-{lastSpec}_iter_{msIter}{corr}"
    fileNameZ = fileName + ".npz"

    bootOutPath = experimentsPath / sampleName / "bootstrap_data"
    
    bootName = fileName + f"_nsampl_{nSamples}"
    bootNameYFit = fileName + "_ySpaceFit" + f"_nsampl_{nSamples}"

    bootNameZ = bootName + ".npz"
    bootNameYFitZ = bootNameYFit + ".npz"

    loadPath = bootOutPath / speed / bootNameZ
    bootData = np.load(loadPath)

    loadYFitPath = bootOutPath / speed / bootNameYFitZ

    return loadPath, loadYFitPath


sampleName = "D_HMT"
firstSpec = 3
lastSpec = 134
msIter = 4
MS = True
GC = False
nSamples = 1000
nBins = 30
speed = "slow"
ySpaceFit = False

# sampleName = "starch_80_RD"
# firstSpec = 3
# lastSpec = 134
# msIter = 1
# MS = True
# GC = False
# nSamples = 40
# nBins = 6
# speed = "slow"
# ySpaceFit = False


dataPath, dataYFitPath = dataPaths(sampleName, firstSpec, lastSpec, msIter, MS, GC, nSamples, speed)

bootData = np.load(dataPath)
bootPars = bootData["boot_samples"][:, :, 1:-2]
parentPars = bootData["parent_result"][:, 1:-2]

checkBootSamplesVSParent(bootPars, parentPars)


meanWp, meanIp, stdWp, stdIp = calcBootMeans(parentPars[np.newaxis, :, :])
meanWp = meanWp.flatten()
meanIp = meanIp.flatten()

meanW, meanI, stdW, stdI = calcBootMeans(bootPars)

fig, axs = plt.subplots(1, 2, figsize=(15, 3))
for ax, means, title, meanp in zip(axs.flatten(), [meanW, meanI], ["Widths", "Intensities"], [meanWp, meanIp]):
    plotHists(ax, means, nBins, title)
    addParentMeans(ax, meanp)
plt.show()


if ySpaceFit:
    bootYFitData = np.load(dataYFitPath)
    bootYFitVals = bootYFitData["boot_vals"]
    mFitVals = bootYFitVals[:, 0, :-1].T  # Last value is chi

    fig, ax = plt.subplots()
    plotHists(ax, mFitVals, nBins, "Y-Space Fit Parameters")
    plt.show()

# plot3DRows(meanW0)
plot2DHists(meanW, nBins, "Widths")    
plot2DHists(meanI, nBins, "Intensities")   

