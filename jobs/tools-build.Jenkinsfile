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
//     ARTIFACTORY_SCRATCH_CRED is a folder-scoped credential in xpum/10_tools/.
//   - Signing is post-merge only; this job never signs artifacts (Core Principle 2).

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

def MATRIX_FILE              = 'build-matrix.yml'   // CI-repo-resident
def PRODUCT_REPO_URL         = 'https://github.com/intel-innersource/libraries.compute.xpu-manager.xpum.git'
def ARTIFACTORY_SCRATCH_CRED = 'artifactory-xpum-scratch'
def SCRATCH_REPO_PATH        = 'xpum-scratch'

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
  Linux   — first linux entry in build-matrix.yml
  Windows — first windows entry in build-matrix.yml
  Both    — first linux + first windows (default validation pair)
  All     — every cell in build-matrix.yml'''
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

// ---------------------------------------------------------------------------
// Build-matrix resolution
//
// build-matrix.yml and pod-templates/ live in this CI repo.
// A k8s-lightweight node checks it out via `checkout scm`, reads the matrix,
// and inlines pod template YAML so build stages can call podTemplate() without
// re-accessing the CI repo workspace.
// ---------------------------------------------------------------------------

def resolveBuildMatrix = {
    def matrix = null

    node('k8s-lightweight') {
        checkout scm

        if (!fileExists(MATRIX_FILE)) {
            error "Build matrix not found: ${MATRIX_FILE}"
        }

        matrix = readYaml(file: MATRIX_FILE)

        matrix?.linux?.each { String distroName, def cfg ->
            if (!cfg?.podTemplate) {
                error "linux.${distroName} in ${MATRIX_FILE} is missing 'podTemplate'"
            }
            if (!fileExists(cfg.podTemplate as String)) {
                error "Pod template not found: ${cfg.podTemplate} (linux.${distroName})"
            }
            cfg.podYamlTemplate = readFile(cfg.podTemplate as String)
        }

        cleanWs()
    }

    if (!matrix) {
        error "Failed to load build matrix from ${MATRIX_FILE}"
    }
    return matrix
}

// ---------------------------------------------------------------------------
// Linux build flow
//
// Allocates a Kubernetes pod from the matrix config, then delegates all
// build commands to xpum.Build and xpum.Artifactory shared library classes.
// ---------------------------------------------------------------------------

def linuxBuildFlow = { Map matrix, String distroName, String buildType ->
    def cfg = matrix?.linux?.get(distroName)
    if (!cfg) {
        error "linux.${distroName} not found in ${MATRIX_FILE}"
    }

    String podYaml = (cfg.podYamlTemplate as String).replace('dockerBuildImageName', cfg.image as String)
    Map podOptions = [yaml: podYaml]
    if (cfg.cloud) {
        podOptions.cloud = cfg.cloud as String
    }

    String artifactDir = "artifacts_Linux_${distroName}_${buildType}"
    String packageDir  = "packages_Linux_${distroName}_${buildType}"

    podTemplate(podOptions) {
        node(POD_LABEL) {
            container((cfg.containerName ?: 'xpum') as String) {
                def build = new xpum.Build(this)
                def art   = new xpum.Artifactory(this)
                try {
                    stage("Linux ${distroName} ${buildType} - Checkout") {
                        build.checkout(PRODUCT_REPO_URL, params.GIT_REF as String)
                    }

                    stage("Linux ${distroName} ${buildType} - Build") {
                        build.buildLinux(buildType)
                    }

                    stage("Linux ${distroName} ${buildType} - Collect") {
                        build.collectArtifacts('Linux', buildType, "build_${buildType}", artifactDir)
                    }

                    stage("Linux ${distroName} ${buildType} - Package") {
                        String commit    = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
                        String timestamp = new Date().format('yyyyMMdd_HHmmss', TimeZone.getTimeZone('UTC'))
                        build.packageArtifacts('Linux', artifactDir, packageDir, commit, timestamp)
                    }

                    if (params.UPLOAD_ARTIFACTS) {
                        stage("Linux ${distroName} ${buildType} - Upload") {
                            String assetPath = "${SCRATCH_REPO_PATH}/${params.GIT_REF}/${env.BUILD_NUMBER}/Linux/${distroName}/${buildType}"
                            art.uploadScratch(ARTIFACTORY_SCRATCH_CRED, assetPath, packageDir)
                        }
                    }

                } finally {
                    stage("Linux ${distroName} ${buildType} - Archive") {
                        archiveArtifacts allowEmptyArchive: true, artifacts: [
                            "${packageDir}/*.tar.gz",
                            "${packageDir}/*.zip",
                            '**/meson-logs/**',
                            '**/*.log'
                        ].join(',')
                        cleanWs()
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Windows build flow
//
// Allocates a static Windows agent from the matrix config, then delegates all
// build commands to xpum.Build and xpum.Artifactory shared library classes.
// ---------------------------------------------------------------------------

def windowsBuildFlow = { Map matrix, String winTarget, String buildType ->
    def cfg = matrix?.windows?.get(winTarget)
    if (!cfg) {
        error "windows.${winTarget} not found in ${MATRIX_FILE}"
    }

    String agentLabel = cfg.agentLabel as String
    if (!agentLabel?.trim()) {
        error "windows.${winTarget} is missing 'agentLabel' in ${MATRIX_FILE}"
    }

    String artifactDir = "artifacts_Windows_${winTarget}_${buildType}"
    String packageDir  = "packages_Windows_${winTarget}_${buildType}"

    node(agentLabel) {
        // Unique workspace subdirectory per cell prevents path collisions when
        // parallel All-platform branches share the same static Windows agent.
        ws("${env.WORKSPACE}@${winTarget}_${buildType}") {
            def build = new xpum.Build(this)
            def art   = new xpum.Artifactory(this)
            try {
                stage("Windows ${winTarget} ${buildType} - Checkout") {
                    cleanWs()
                    build.checkout(PRODUCT_REPO_URL, params.GIT_REF as String)
                }

                String commit    = powershell(returnStdout: true, script: 'git rev-parse HEAD').trim()
                String timestamp = new Date().format('yyyyMMdd_HHmmss', TimeZone.getTimeZone('UTC'))

                stage("Windows ${winTarget} ${buildType} - Build") {
                    build.buildWindows(buildType)
                }

                stage("Windows ${winTarget} ${buildType} - Collect") {
                    build.collectArtifacts('Windows', buildType, "build_${buildType}", artifactDir)
                }

                stage("Windows ${winTarget} ${buildType} - Package") {
                    build.packageArtifacts('Windows', artifactDir, packageDir, commit, timestamp)
                }

                if (params.UPLOAD_ARTIFACTS) {
                    stage("Windows ${winTarget} ${buildType} - Upload") {
                        String assetPath = "${SCRATCH_REPO_PATH}/${params.GIT_REF}/${env.BUILD_NUMBER}/Windows/${winTarget}/${buildType}"
                        art.uploadScratch(ARTIFACTORY_SCRATCH_CRED, assetPath, packageDir)
                    }
                }

            } finally {
                stage("Windows ${winTarget} ${buildType} - Archive") {
                    archiveArtifacts allowEmptyArchive: true, artifacts: [
                        "${packageDir}\\*.exe",
                        "${packageDir}\\*.msi",
                        "${packageDir}\\*.zip",
                        '**\\meson-logs\\**',
                        '**\\*.log'
                    ].join(',')
                    cleanWs()
                }
            }
        }
    }
}

// Expand BUILD_TYPE 'both' into ['release', 'debug']; pass through otherwise.
def expandBuildTypes = { String buildType ->
    buildType == 'both' ? ['release', 'debug'] : [buildType]
}

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
        echo "BUILD_TYPE:       ${params.BUILD_TYPE}"
        echo "UPLOAD_ARTIFACTS: ${params.UPLOAD_ARTIFACTS}"
        echo "==================="
    }

    def matrix
    stage('Resolve Matrix') {
        matrix = resolveBuildMatrix()
    }

    stage('Build') {
        List<String> buildTypes = expandBuildTypes(params.BUILD_TYPE as String)
        boolean      allCells   = params.PLATFORM == 'All'

        def linuxTargets = []
        if (params.PLATFORM in ['Linux', 'Both', 'All']) {
            def keys = matrix?.linux?.keySet()?.sort() ?: []
            linuxTargets = allCells ? keys : (keys ? [keys.first()] : [])
        }

        def windowsTargets = []
        if (params.PLATFORM in ['Windows', 'Both', 'All']) {
            def keys = matrix?.windows?.keySet()?.sort() ?: []
            windowsTargets = allCells ? keys : (keys ? [keys.first()] : [])
        }

        def branches = [:]

        linuxTargets.each { distroName ->
            buildTypes.each { bt ->
                branches["Linux-${distroName}-${bt}"] = {
                    linuxBuildFlow(matrix, distroName as String, bt)
                }
            }
        }

        windowsTargets.each { winTarget ->
            buildTypes.each { bt ->
                branches["Windows-${winTarget}-${bt}"] = {
                    windowsBuildFlow(matrix, winTarget as String, bt)
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
