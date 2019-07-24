# International geography audit

The investigation covered Serbia and Montenegro's 2006 dissolution, the Netherlands Antilles' 2010 dissolution and Sudan's 2011 partition. The M49 change notes establish the transition dates and successor statistical codes. WDI values attached to current codes can describe earlier reference years. Their existence does not establish how the series were reconstructed.

The verifier checked 1,029 coverage cells across seven successor codes, seven metrics, six archives and the current panel. Of 7,350 underlying rows, 1,961 nonmissing observations fell before or during a recognized territory change. The audit withheld nine values with reference years beyond their archive series bounds. Missing reported cells are distinguished from entities that have no row. The audit transfers zero historical event counts and uses no assumed population weights. It records where exact source definitions would be needed to join predecessor and successor trajectories.

The audit is available as `make territory-audit` after restoring the current and archived WDI panels with `make data`. It independently reconstructs the counts from the original data dimensions. The wider worldwide boundary and original daily release history remains incomplete.

[UN M49 change notes](https://unstats.un.org/unsd/methodology/m49/) · [World Bank WDI archives](https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html)
