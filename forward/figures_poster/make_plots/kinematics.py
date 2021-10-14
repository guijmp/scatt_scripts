import unittest
import numpy as np
import numpy.testing as nptest
import matplotlib.pyplot as plt
from mantid.simpleapi import *    
from pathlib import Path
currentPath = Path(__file__).absolute().parent  # Path to the repository

# from jupyterthemes import jtplot
# jtplot.style()

dataPath = currentPath / "data_for_plots.npz"

class TestPlots(unittest.TestCase):
    def setUp(self):
        results = np.load(dataPath)
        self.masses = results["masses"]
        self.hbar = 2.0445
        spec = 11
        self.dataY = results["all_dataY"][0, spec]    # In the order of the script
        self.dataX = results["all_dataX"][0, spec]
        self.dataE = results["all_dataE"][0, spec]
        self.deltaQ = results["all_deltaQ"][0, spec]
        self.deltaE = results["all_deltaE"][0, spec]
        self.yspaces_for_each_mass = results["all_yspaces_for_each_mass"][0, spec]
        self.spec_best_par_chi_nit = results["all_spec_best_par_chi_nit"][0, spec]
        self.mean_widths = results["all_mean_widths"][0]
        self.mean_intensities = results["all_mean_intensities"][0]
        self.tot_ncp = results["all_tot_ncp"][0, spec]
        self.ncp_for_each_mass = results["all_ncp_for_each_mass"][0, spec]

    def test_TOF_plot(self):
        plt.figure()
        plt.errorbar(self.dataX, self.dataY, yerr=self.dataE,
                    fmt="none", label="Data", linewidth=1, color="orange")
        for i, ncp_m in enumerate(self.ncp_for_each_mass):
            plt.plot(self.dataX, ncp_m, label=f"NCP mass {self.masses[i]}")
        
        plt.plot(self.dataX, self.tot_ncp, label="NCP total fit",
                 linestyle="--", color="black" )

        plt.xlabel("TOF")
        plt.ylabel("C(t)")
        plt.legend()

    def test_structure_factor_plot(self):
        ax = plt.figure().add_subplot(projection='3d')
        #ax.errorbar(deltaq, deltaw, datay, datae)
        #ax.scatter3D(self.deltaQ, self.deltaE, self.dataY, label="Data")
        ax.plot3D(self.deltaQ, self.deltaE, self.tot_ncp, label="Total NCP fit" )
        
        for i, ncp_m in enumerate(self.ncp_for_each_mass):
            ax.plot3D(self.deltaQ, self.deltaE, ncp_m, label=f"NCP mass {self.masses[i]}")
        
        for m in self.masses:
            ax.plot3D(self.deltaQ, self.hbar**2*self.deltaQ**2/2/m, 0, label=f"mass: {m}")
        ax.set_xlabel("q")
        ax.set_ylabel("w")
        ax.set_zlabel("S(q,w)")
        plt.legend()
        plt.show()
    
    # def test_ncp_yspace(self):
    #     for m, yspace_m, ncp_m in zip(self.masses, self.yspaces_for_each_mass, self.ncp_for_each_mass):
    #         plt.figure()
    #         plt.plot(yspace_m, ncp_m, label=f"NCP for mass {m}")
    #         plt.errorbar(yspace_m, self.dataY, yerr=self.dataE, fmt="none", label="Data")
    #         plt.xlabel(f"yspace for mass={m}")
    #         plt.legend()
    #         plt.show()

if __name__ == "__main__":
    unittest.main()