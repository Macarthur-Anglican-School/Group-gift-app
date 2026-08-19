#!/bin/bash

#IMPORTANT: ensure you are in the project root directory before running this script

# 1. Create the folder structure
echo "🏗️ Building CyberWatch folder structure..."
for line in $(cat .setup/folders.txt);
do
    echo $line;
    mkdir -p $line;
done

# 2. Move files into their correct homes
echo "🚚 Organizing project files..."
mv cyberwatch.sqlite3-query .database/ 2>/dev/null
mv script.js static/js/ 2>/dev/null
mv *.html templates/ 2>/dev/null

# 3. Create placeholder files if they don't exist
touch static/css/styles.css
touch static/icons/icon-192.png static/icons/icon-512.png
#TO DO
#make the manifest.json file in the static folder
touch manifest.json
#make the service-worker.js file in the static/js folder
touch service-worker.js


echo "✅ Project Ready! Use 'ls -R' to verify."