#!/usr/bin/env bash

set -euo pipefail

# download the code package

clone_repo_at_commit() {
	local repo_url=$1
	local repo_dir=$2
	local target_commit=$3
	local target_branch=${4:-}

	rm -fr "${repo_dir}"
	if [ -n "${target_branch}" ]; then
		git clone --depth=1 -b "${target_branch}" "${repo_url}" "${repo_dir}"
	else
		git clone --depth=1 "${repo_url}" "${repo_dir}"
	fi
	(
		cd "${repo_dir}"
		git fetch --depth=1 origin "${target_commit}"
		git checkout "${target_commit}"
		test "$(git rev-parse HEAD)" = "${target_commit}"
	)
	rm -fr "${repo_dir}/.git"
}

# download 3DMCGlauber
clone_repo_at_commit \
	https://github.com/mluzum/3dMCGlauber \
	3dMCGlauber_code \
	1d9856c6ce2bbad28059ed8815ebdf246aa37cdf

# download IPGlasma
clone_repo_at_commit \
	https://github.com/chunshen1987/ipglasma \
	ipglasma_code \
	bf92fe1758a61acc5cf84dff2428b83570ea81fa \
	ipglasma_jimwlk

# download KoMPoST
clone_repo_at_commit \
	https://github.com/chunshen1987/KoMPoST \
	kompost_code \
	ad5fe9d3b26434bb1d5c29820499ef26808b5a47

# download MUSIC
clone_repo_at_commit \
	https://github.com/MUSIC-fluid/MUSIC \
	MUSIC_code \
	84734adf838fdf2ed9b0c9951916614e7c925950 \
	main

# download iSS particle sampler
clone_repo_at_commit \
	https://github.com/chunshen1987/iSS \
	iSS_code \
	b612a8e425d3e1dfc2d2b71cd208df6810c783be \
	dev

# download photonEmission wrapper
clone_repo_at_commit \
	https://github.com/chunshen1987/photonEmission_hydroInterface \
	photonEmission_hydroInterface_code \
	b80fb78c154cc9131162c8205615faffc86d6a49

# download UrQMD afterburner
clone_repo_at_commit \
	https://Chunshen1987@bitbucket.org/Chunshen1987/urqmd_afterburner.git \
	urqmd_code \
	09eeac28b5861d68d166c1f89b2e97e0a0ebfe8f

# download hadronic afterner
clone_repo_at_commit \
	https://github.com/chunshen1987/hadronic_afterburner_toolkit \
	hadronic_afterburner_toolkit_code \
	2326ba21a76d7bb533aa1d39a50f3dca298ef9c3 \
	main

# download nucleus configurations for 3D-Glauber
(cd 3dMCGlauber_code/tables; bash download_nucleusTables.sh;)
# download nucleus configurations for IP-Glasma
(cd ipglasma_code/nucleusConfigurations; bash download_nucleusTables.sh;)
# download essential EOS files for hydro simulations
(cd MUSIC_code/EOS; bash download_hotQCD.sh; bash download_Neos2D.sh bqs;)
