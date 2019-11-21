String cron_format = env.BRANCH_NAME == 'master' ? '00 10 * * *' : ''

pipeline {
    agent any
 
    options {
        buildDiscarder logRotator(artifactDaysToKeepStr: '', artifactNumToKeepStr: '', daysToKeepStr: '7', numToKeepStr: '5')
    }

    environment {
        def unique_name = "gcp-core-team-${deployment}-${env.CHANGE_ID}"
        def component_name = "ip-enforcer"
    }
 
    triggers {
        cron(cron_format)
    }

    stages {
        stage('Configure Git') {
            steps {
                withCredentials(bindings: [usernamePassword(credentialsId: 'github-un', usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD')]) {
                    sh "git config --global credential.username ${GIT_USERNAME}"
                    sh "git config --global credential.helper '!echo password=${GIT_PASSWORD}; echo'"
                }
            }
        }

        stage('Run Unit Tests') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    try {
                        sh '''
                            python -m virtualenv ${BUILD_TAG} > /dev/null 2>&1
                            source ${BUILD_TAG}/bin/activate > /dev/null 2>&1
                            cd enforcer && pip install -r tests/requirements.txt
                        '''
                        def unit_tests = sh (
                            script: '''
                                source ${BUILD_TAG}/bin/activate > /dev/null 2>&1
                                cd enforcer && python -m pytest tests/ --cov-report term-missing --cov='.'
                            ''',
                            returnStdout: true
                        ).trim()

                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test(s) Success:\n\n${unit_tests}")
                        }

                    } catch (Exception e) {
                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test Environment Configuration Error. ${e}")
                        }
                        error "Unit Test Environment Configuration Error. ${e}"
                    }
                }
            }
        }

        stage('Packer Build GCE Image(s)') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {                 
                    sh "packer build packer.json"                             
                }
            }
        }

        stage('Deploy Test: Rolling Replace (gcloud)') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    sh "gcloud --project=gcp-core-team-test compute instance-groups managed rolling-action replace gce-igm-europe-west1-t-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=gcp-core-team-test compute instance-groups managed wait-until gce-igm-europe-west1-t-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }

        stage('Copy GCE Image to Dev') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    try {
                        def latest_image = sh (
                            script: "gcloud --project=gcp-core-team-test compute images list \
                            --format='value(NAME)' --filter=family:ocean-ip-enforcer \
                            --sort-by=createTime --limit=1",
                            returnStdout: true
                        ).trim()
                                       
                        def now = new Date()
                        sh (
                            script: "gcloud --project=gcp-core-team-dev compute images create ocean-ip-enforcer-${now.format('yyyyMMddHHmmss')} \
                            --family ocean-ip-enforcer \
                            --source-image=${latest_image} \
                            --source-image-project=gcp-core-team-test --quiet",
                            returnStatus: true
                        )
                    } catch (Exception e) {
                        sh "echo ${e}"
                    } 
                }
            }
        }

        stage('Deploy Dev: Rolling Replace') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    def deployment = "dev"
                    sh "gcloud --project=gcp-core-team-${deployment} compute instance-groups managed rolling-action replace gce-igm-europe-west1-d-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=gcp-core-team-${deployment} compute instance-groups managed wait-until gce-igm-europe-west1-d-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }

        stage('Copy GCE Image to Prod') {
            when { 
                changeRequest target: 'prod' 
            }
            steps {
                script {
                    try {
                        def latest_image = sh (
                            script: "gcloud --project=gcp-core-team-dev compute images list \
                            --format='value(NAME)' --filter=family:ocean-ip-enforcer \
                            --sort-by=createTime --limit=1",
                            returnStdout: true
                        ).trim()
                    
                        def now = new Date()
                        sh (
                            script: "gcloud --project=gcp-core-team-prod compute images create ocean-ip-enforcer-${now.format('yyyyMMddHHmmss')} \
                            --family ocean-ip-enforcer \
                            --source-image=${latest_image} \
                            --source-image-project=gcp-core-team-test --quiet",
                            returnStatus: true
                        )
                    } catch (Exception e) {
                        sh "echo ${e}"
                    }
                }
            }
        }

        stage('Deploy Prod: Rolling Replace') {
            when { 
                changeRequest target: 'prod' 
            }
            steps {
                script {
                    def deployment = "prod"
                    sh "gcloud --project=gcp-core-team-${deployment} compute instance-groups managed rolling-action replace gce-igm-europe-west1-d-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=gcp-core-team-${deployment} compute instance-groups managed wait-until gce-igm-europe-west1-d-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }
    }

    post {
        success {
            script {
                // Store last successful commit in GCS
                if (env.GIT_BRANCH == 'master') {
                    sh "echo ${env.GIT_COMMIT} > /tmp/last-successful-commit"
                    sh 'gsutil cp /tmp/last-successful-commit gs://jenkins-build-files-mq/successful-commits/ip-enforcer'
                    sh 'rm -f /tmp/last-successful-commit'
                }

                cleanWs()
            }
        }
        cleanup {
            script {
                try {
                    sh 'git config --global --unset credential.helper'
                } catch(Exception e) {}

                cleanWs()
            }
        }
    }
}
