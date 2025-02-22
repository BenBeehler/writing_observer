#!/usr/bin/env bash
# ===============================
# RunLearningObserver.sh
# Collin F. Lynch
#
# This bash script provides a simple wrapper to run the 
# learning observer service and pipe the data to a logfile
# over time this should be integrated into the systemd 
# service process.  This uses static variables to specify
# the location of the virtualenv and the command and 
# specifies the location for the running logfile. 

# System Variables
# --------------------------------------
VIRTUALENV_PYTHON="/usr/local/share/Projects/WritingObserver/VirtualENVs/learning_observer/bin/python3.8"
LEARNING_OBSERVER_LOC="/usr/local/share/Projects/WritingObserver/Repo-Fork/writing_observer/learning_observer"
LOGFILE_DEST="/usr/local/share/Projects/WritingObserver/Repo-Fork/writing_observer/learning_observer/learning_observer/logs"

# Make the logfile name
# ---------------------------------------
LOG_DATE=$(date "+%m-%d-%Y--%H-%M-%S")
LOGFILE_NAME="$LOGFILE_DEST/learning_observer_service_$LOG_DATE.log"
echo $LOG_NAME;

 
# Now run the thing.
# --------------------------------------
echo "Running Learning Observer Service..."
cd $LEARNING_OBSERVER_LOC
#$($VIRTUALENV_PYTHON $LEARNING_OBSERVER_LOC > $LOG_NAME 2>&1)
nohup $VIRTUALENV_PYTHON learning_observer > $LOGFILE_NAME 2>&1 &
echo $! > $LOGFILE_DEST/run.pid
