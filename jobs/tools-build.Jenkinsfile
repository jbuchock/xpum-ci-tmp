// xpum/10_tools/build — On-demand build for Linux and/or Windows.
//
// Thin orchestrator: agent allocation, matrix dispatch, and stage sequencing
// live here.  All build/collect/package/upload commands are delegated to the
// shared library (src/xpum/Build.groovy, src/xpum/Artifactory.groovy).
//
// Core principles observed:
//   - Build matrix (build-matrix.yml) and pod templates reside in this CI repo.
//     No product-repo checkout is needed to resolve config (Core Principle 5 delta).
//   - Credentials come from the Jenkins credential store only (Core Principle 3).
//     ARTIFACTORY_CRED is a folder-scoped credential in xpum/10_tools/.
//   - Signing is post-merge only; this job never signs artifacts (Core Principle 2).

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

def MATRIX_FILE              = 'build-matrix.yml'   // CI-repo-resident
def PRODUCT_REPO_URL         = 'https://github.com/intel-innersource/libraries.compute.xpu-manager.xpum.git'
def ARTIFACTORY_CRED         = 'artifactory-xpum'
def ARTIFACTORY_REPO        = 'gfx-xpu-manager'

// ---------------------------------------------------------------------------
// Job properties
// ---------------------------------------------------------------------------

properties([
    disableConcurrentBuilds(),
    buildDiscarder(logRotator(numToKeepStr: '50')),
    parameters([
        string(
            name:         'GIT_REF',
            defaultValue: 'dev',
            description:  'Product-repo branch, tag, or SHA to build'
        ),
        choice(
            name:    'PLATFORM',
            choices: ['Both', 'Linux', 'Windows', 'All'],
            description: '''\
Target platform:
    Linux   — build selected LINUX_DISTRO (or first key when set to auto)
    Windows — build selected WINDOWS_TARGET (or first key when set to auto)
    Both    — build selected LINUX_DISTRO + selected WINDOWS_TARGET
    All     — every cell in build-matrix.yml'''
        ),
        string(
            name:         'LINUX_DISTRO',
            defaultValue: 'auto',
            description:  'Linux matrix key to build (e.g. ubuntu24.04). Use "auto" for first key.'
        ),
        string(
            name:         'WINDOWS_TARGET',
            defaultValue: 'auto',
            description:  'Windows matrix key to build (e.g. server2022). Use "auto" for first key.'
        ),
        choice(
            name:        'BUILD_TYPE',
            choices:     ['release', 'debug', 'both'],
            description: 'Build type.  "both" fans out to parallel release + debug branches.'
        ),
        booleanParam(
            name:         'UPLOAD_ARTIFACTS',
            defaultValue: false,
            description:  'Upload packaged artifacts to the Artifactory scratch path (xpum-scratch/)'
        )
    ])
])

// Reusable matrix resolution and per-cell Linux/Windows flows are in
// vars/xpumLib.groovy to keep this job as a thin orchestrator.

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

timeout(time: 90, unit: 'MINUTES') {

    stage('Init') {
        currentBuild.displayName = "#${env.BUILD_NUMBER} [${params.PLATFORM}|${params.BUILD_TYPE}|${params.GIT_REF}]"
        currentBuild.description = "Platform=${params.PLATFORM}  BuildType=${params.BUILD_TYPE}  Upload=${params.UPLOAD_ARTIFACTS}"
        echo "=== tools-build ==="
        echo "GIT_REF:          ${params.GIT_REF}"
        echo "PLATFORM:         ${params.PLATFORM}"
        echo "LINUX_DISTRO:     ${params.LINUX_DISTRO}"
        echo "WINDOWS_TARGET:   ${params.WINDOWS_TARGET}"
        echo "BUILD_TYPE:       ${params.BUILD_TYPE}"
        echo "UPLOAD_ARTIFACTS: ${params.UPLOAD_ARTIFACTS}"
        echo "==================="
    }

    def matrix
    stage('Resolve Matrix') {
        matrix = xpumLib.resolveBuildMatrix(
            matrixFile: MATRIX_FILE,
            resolverLabel: 'k8s-lightweight'
        )
    }

    stage('Build') {
        List<String> buildTypes = xpumLib.expandBuildTypes(params.BUILD_TYPE as String)
        boolean      allCells   = params.PLATFORM == 'All'

        def resolveSingleTarget = { List<String> keys, String selected, String kind ->
            if (!keys) {
                return []
            }

            String trimmed = (selected ?: 'auto').trim()
            if (!trimmed || trimmed.equalsIgnoreCase('auto')) {
                return [keys.first()]
            }

            if (!keys.contains(trimmed)) {
                error "${kind} target '${trimmed}' not found in ${MATRIX_FILE}. Available: ${keys.join(', ')}"
            }

            return [trimmed]
        }

        def linuxTargets = []
        if (params.PLATFORM in ['Linux', 'Both', 'All']) {
            def keys = matrix?.linux?.keySet()?.sort() ?: []
            linuxTargets = allCells ? keys : resolveSingleTarget(keys, params.LINUX_DISTRO as String, 'Linux')
        }

        def windowsTargets = []
        if (params.PLATFORM in ['Windows', 'Both', 'All']) {
            def keys = matrix?.windows?.keySet()?.sort() ?: []
            windowsTargets = allCells ? keys : resolveSingleTarget(keys, params.WINDOWS_TARGET as String, 'Windows')
        }

        def branches = [:]

        linuxTargets.each { distroName ->
            buildTypes.each { bt ->
                branches["Linux-${distroName}-${bt}"] = {
                    xpumLib.runLinuxBuildCell(
                        matrix: matrix,
                        distroName: distroName as String,
                        buildType: bt,
                        matrixFile: MATRIX_FILE,
                        productRepoUrl: PRODUCT_REPO_URL,
                        gitRef: params.GIT_REF as String,
                        uploadArtifacts: params.UPLOAD_ARTIFACTS as boolean,
                        artifactoryRepo: ARTIFACTORY_REPO,
                        artifactoryCred: ARTIFACTORY_CRED
                    )
                }
            }
        }

        windowsTargets.each { winTarget ->
            buildTypes.each { bt ->
                branches["Windows-${winTarget}-${bt}"] = {
                    xpumLib.runWindowsBuildCell(
                        matrix: matrix,
                        winTarget: winTarget as String,
                        buildType: bt,
                        matrixFile: MATRIX_FILE,
                        productRepoUrl: PRODUCT_REPO_URL,
                        gitRef: params.GIT_REF as String,
                        uploadArtifacts: params.UPLOAD_ARTIFACTS as boolean,
                        artifactoryRepo: ARTIFACTORY_REPO,
                        artifactoryCred: ARTIFACTORY_CRED
                    )
                }
            }
        }

        if (branches.isEmpty()) {
            error "No build targets resolved for PLATFORM='${params.PLATFORM}'. Verify ${MATRIX_FILE}."
        }

        branches.failFast = true
        parallel branches
    }
}
