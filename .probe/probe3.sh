# Midlertidig: kører den rigtige opskrifthentning på en kopi af samlingen
set -e
cp src/tilbudshenter/data/opskrifter.json /tmp/samling.json
time tilbudshenter opskrifter --liste opskrifter.txt --ud /tmp/samling.json
