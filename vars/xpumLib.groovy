// Shared pipeline entrypoints for XPUM CI jobs.
// Keep orchestration thin in Jenkinsfiles while centralizing reusable logic.

private String pickResolverLabel() {
    List<String> candidates = ['k8s-lightweight', 'controller-node']
    for (String label : candidates) {
        if (nodesByLabel(label: label, offline: false)) {
            return label
        }
    }
    error "No resolver agent available. Tried: ${candidates.join(', ')}"
}

def resolveBuildMatrix(Map args = [:]) {
    String matrixFile = (args.matrixFile ?: 'build-matrix.yml') as String
    String resolverLabel = (args.resolverLabel ?: 'k8s-lightweight') as String

    def matrix = null

    node(pickResolverLabel()) {
        try {
            checkout scm

            if (!fileExists(matrixFile)) {
                error "Build matrix not found: ${matrixFile}"
            }

            matrix = readYaml(file: matrixFile)

            matrix?.linux?.each { String distroName, def cfg ->
                if (!cfg?.podTemplate) {
                    error "linux.${distroName} in ${matrixFile} is missing 'podTemplate'"
                }
                if (!fileExists(cfg.podTemplate as String)) {
                    error "Pod template not found: ${cfg.podTemplate} (linux.${distroName})"
                }
                cfg.podYamlTemplate = readFile(cfg.podTemplate as String)
            }
            steps.stash(name: 'ci-scripts', includes: 'scripts/**')
        } finally {
            cleanWs()
        }
    }

    if (!matrix) {
        error "Failed to load build matrix from ${matrixFile}"
    }

    return matrix
}

def expandBuildTypes(String buildType) {
    buildType == 'both' ? ['release', 'debug'] : [buildType]
}

def runLinuxBuildCell(Map args) {
    Map matrix = args.matrix as Map
    String distroName = args.distroName as String
    String buildType = args.buildType as String
    String matrixFile = (args.matrixFile ?: 'build-matrix.yml') as String
    String productRepoUrl = args.productRepoUrl as String
    String gitRef = args.gitRef as String
    String artifactoryRepo = (args.artifactoryRepo ?: 'gfx-xpu-manager') as String
    String artifactoryCred = args.artifactoryCred as String
    boolean pushArtifacts = (args.pushArtifacts ?: false) as boolean
    boolean keepArtifacts = (args.keepArtifacts ?: false) as boolean

    def cfg = matrix?.linux?.get(distroName)
    if (!cfg) {
        error "linux.${distroName} not found in ${matrixFile}"
    }

    String scriptBt = toScriptBuildType(buildType)
    String podYaml = (cfg.podYamlTemplate as String).replace('dockerBuildImageName', cfg.image as String)
    Map podOptions = [yaml: podYaml]
    if (cfg.cloud) {
        podOptions.cloud = cfg.cloud as String
    }

    String artifactDir = "artifacts_Linux_${distroName}_${buildType}"
    String packageDir = "packages_Linux_${distroName}_${buildType}"

    podTemplate(podOptions) {
        node(POD_LABEL) {
            container((cfg.containerName ?: 'xpum') as String) {
                def build = new xpum.Build(this)
                def art = new xpum.Artifactory(this)
                try {
                    stage("Linux ${distroName} ${buildType} - Checkout") {
                        build.checkout(productRepoUrl, gitRef)
                        dir('jenkins') {
                            unstash 'ci-scripts'   // lands as jenkins/scripts/build_xpum.py
                        }
                    }

                    stage("Linux ${distroName} ${buildType} - Build") {
                        build.buildLinux(scriptBt)
                    }

                    stage("Linux ${distroName} ${buildType} - Collect") {
                        build.collectArtifacts('Linux', scriptBt, "build_${scriptBt}", artifactDir)
                    }

                    stage("Linux ${distroName} ${buildType} - Package") {
                        String commit = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
                        String timestamp = new Date().format('yyyyMMdd_HHmmss', TimeZone.getTimeZone('UTC'))
                        build.packageArtifacts('Linux', artifactDir, packageDir, commit, timestamp)
                    }

                    if (pushArtifacts) {
                        stage("Linux ${distroName} ${buildType} - Upload") {
                            String assetPath = "${artifactoryRepo}/test/jbuchock/${env.BUILD_NUMBER}/Linux"
                            art.pushToArtifactory(artifactoryCred, assetPath, distroName, scriptBt, packageDir)
                        }
                    }

                } finally {
                    stage("Linux ${distroName} ${buildType} - Archive") {
                        if (keepArtifacts) {
                            archiveArtifacts allowEmptyArchive: true, artifacts: [
                                "${packageDir}/*.tar.gz",
                                "${packageDir}/*.zip",
                                '**/meson-logs/**',
                                '**/*.log'
                            ].join(',')
                        }

                        cleanWs()
                    }
                }
            }
        }
    }
}

def runWindowsBuildCell(Map args) {
    Map matrix = args.matrix as Map
    String winTarget = args.winTarget as String
    String buildType = args.buildType as String
    String matrixFile = (args.matrixFile ?: 'build-matrix.yml') as String
    String productRepoUrl = args.productRepoUrl as String
    String gitRef = args.gitRef as String
    String artifactoryRepo = (args.artifactoryRepo ?: 'gfx-xpu-manager') as String
    String artifactoryCred = args.artifactoryCred as String
    boolean pushArtifacts = (args.pushArtifacts ?: false) as boolean
    boolean keepArtifacts = (args.keepArtifacts ?: false) as boolean

    def cfg = matrix?.windows?.get(winTarget)
    if (!cfg) {
        error "windows.${winTarget} not found in ${matrixFile}"
    }

    String agentLabel = cfg.agentLabel as String
    if (!agentLabel?.trim()) {
        error "windows.${winTarget} is missing 'agentLabel' in ${matrixFile}"
    }

    String scriptBt = toScriptBuildType(buildType)
    String artifactDir = "artifacts_Windows_${winTarget}_${buildType}"
    String packageDir = "packages_Windows_${winTarget}_${buildType}"

    node(agentLabel) {
        // Isolate per-cell workspaces when the same static node runs parallel cells.
        ws("${env.WORKSPACE}@${winTarget}_${buildType}") {
            def build = new xpum.Build(this)
            def art = new xpum.Artifactory(this)
            try {
                stage("Windows ${winTarget} ${buildType} - Checkout") {
                    cleanWs()
                    build.checkout(productRepoUrl, gitRef)
                    dir('jenkins') {
                        unstash 'ci-scripts'   // lands as jenkins/scripts/build_xpum.py
                    }
                }

                String commit = powershell(returnStdout: true, script: 'git rev-parse HEAD').trim()
                String timestamp = new Date().format('yyyyMMdd_HHmmss', TimeZone.getTimeZone('UTC'))

                stage("Windows ${winTarget} ${buildType} - Build") {
                    build.buildWindows(scriptBt)
                }

                stage("Windows ${winTarget} ${buildType} - Collect") {
                    build.collectArtifacts('Windows', scriptBt, "build_${scriptBt}", artifactDir)
                }

                stage("Windows ${winTarget} ${buildType} - Package") {
                    build.packageArtifacts('Windows', artifactDir, packageDir, commit, timestamp)
                }

                if (pushArtifacts) {
                    stage("Windows ${winTarget} ${buildType} - Upload") {
                        String assetPath = "${artifactoryRepo}/${gitRef}/${env.BUILD_NUMBER}/Windows"
                        art.pushToArtifactory(artifactoryCred, assetPath, winTarget, scriptBt, packageDir)
                    }
                }

            } finally {
                stage("Windows ${winTarget} ${buildType} - Archive") {
                    if (keepArtifacts) {
                        archiveArtifacts allowEmptyArchive: true, artifacts: [
                            "${packageDir}\\*.exe",
                            "${packageDir}\\*.msi",
                            "${packageDir}\\*.zip",
                            '**\\meson-logs\\**',
                            '**\\*.log'
                        ].join(',')
                    }
                    cleanWs()
                }
            }
        }
    }
}

private String toScriptBuildType(String buildType) {
    switch ((buildType ?: '').toLowerCase()) {
        case 'release':
            return 'Release'
        case 'debug':
            return 'Debug'
        default:
            error "Unsupported BUILD_TYPE='${buildType}'. Expected release or debug."
    }
}
