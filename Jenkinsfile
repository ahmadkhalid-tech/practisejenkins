pipeline {
    agent any

    stages {
        stage('Install') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            python3 -m venv .venv
                            . .venv/bin/activate
                            pip install --upgrade pip
                            pip install -r requirements.txt
                        '''
                    } else {
                        bat '''
                            python -m venv .venv
                            call .venv\\Scripts\\activate
                            python -m pip install --upgrade pip
                            pip install -r requirements.txt
                        '''
                    }
                }
            }
        }

        stage('Test') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            . .venv/bin/activate
                            python app.py --test
                        '''
                    } else {
                        bat '''
                            call .venv\\Scripts\\activate
                            python app.py --test
                        '''
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'test-results.json', fingerprint: true, allowEmptyArchive: false
        }
    }
}