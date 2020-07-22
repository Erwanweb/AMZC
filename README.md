# AMZC

install :

cd ~/domoticz/plugins

mkdir AMZC

sudo apt-get update

sudo apt-get install git

git clone https://github.com/Erwanweb/AMZC.git AMZC

cd AMZC

sudo chmod +x plugin.py

sudo /etc/init.d/domoticz.sh restart

Upgrade :

cd ~/domoticz/plugins/AMZC

git reset --hard

git pull --force

sudo chmod +x plugin.py

sudo /etc/init.d/domoticz.sh restart
