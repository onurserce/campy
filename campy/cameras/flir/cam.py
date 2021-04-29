"""
Onur Serce
Circuits of Emotion Research Group (Gogolla lab)
Max Planck Institute of Neurobiology Munich
"""

import os
import time
import logging
import sys
import csv
import numpy as np
import PySpin
from collections import deque
from CameraPreparation import prepare_camera


def OpenCamera(cam_params, bufferSize=100, validation=False):
    n_cam = cam_params["n_cam"]
    cam_index = cam_params["cameraSelection"]
    camera_name = cam_params["cameraName"]

    # Open and load features for all cameras
    system = PySpin.System.GetInstance()
    cameras = system.GetCameras()
    camera = cameras[cam_index]
    camera.DeInit()
    camera.Init()
    prepare_camera(camera, exposure_time=cam_params['exposure'], gain=cam_params['gain'], trigger_type='hardware',
                   bufferMode='OldestFirst', bufferSize=bufferSize)  # Buffer is set here

    # Get camera information and save to cam_params for metadata
    # Get serial number
    serial = ''
    if camera.TLDevice.DeviceSerialNumber.GetAccessMode() == PySpin.RO:
        serial = camera.TLDevice.DeviceSerialNumber.GetValue()
    cam_params['cameraSerialNo'] = serial

    # Get device display name
    device_display_name = ''
    if PySpin.IsReadable(camera.TLDevice.DeviceDisplayName):
        device_display_name = camera.TLDevice.DeviceDisplayName.ToString()
    cam_params['cameraModel'] = device_display_name

    # Set features manually or automatically, depending on configuration
    cam_params['frameWidth'] = camera.Width.ToString()
    cam_params['frameHeight'] = camera.Height.ToString()

    # Buffer was set above during prepare_camera call
    print("Started", camera_name, "serial#", serial)

    return camera, cam_params


def GrabFrames(cam_params, camera, writeQueue, dispQueue, stopQueue):
    n_cam = cam_params["n_cam"]

    cnt = 0
    timeout = 0

    # Create dictionary for appending frame number and timestamp information
    grabdata = {'timeStamp': [], 'frameNumber': []}

    numImagesToGrab = cam_params['recTimeInSec'] * cam_params['frameRate']
    chunkLengthInFrames = int(round(cam_params["chunkLengthInSec"] * cam_params['frameRate']))

    if cam_params["displayFrameRate"] <= 0:
        frameRatio = float('inf')
    elif cam_params["displayFrameRate"] > 0 and cam_params["displayFrameRate"] <= cam_params['frameRate']:
        frameRatio = int(round(cam_params['frameRate'] / cam_params["displayFrameRate"]))
    else:
        frameRatio = cam_params['frameRate']

    # ToDo: Frame display part
    # if sys.platform == 'win32':
    #     imageWindow = pylon.PylonImageWindow()
    #     imageWindow.Create(n_cam)
    #     imageWindow.Show()

    camera.BeginAcquisition()
    print(cam_params["cameraName"], "ready to trigger.")

    while (camera.IsStreaming()):
        if stopQueue or cnt >= numImagesToGrab:
            CloseCamera(cam_params, camera, grabdata)
            writeQueue.append('STOP')
            break
        try:
            # Grab image from camera buffer if available
            grabResult = camera.GetNextImage(timeout)
            chunkData = grabResult.GetChunkData()

            # Append numpy array to writeQueue for writer to append to file
            writeQueue.append(grabResult.GetNDArray())

            if cnt == 0:
                timeFirstGrab = chunkData.GetTimestamp()
            grabtime = (chunkData.GetTimestamp() - timeFirstGrab) / 1e9
            grabdata['timeStamp'].append(grabtime)

            cnt += 1
            grabdata['frameNumber'].append(cnt)  # first frame = 1

            if cnt % frameRatio == 0:
                dispQueue.append(grabResult.Array[::cam_params["displayDownsample"],
                                 ::cam_params["displayDownsample"]])
            grabResult.Release()

            if cnt % chunkLengthInFrames == 0:
                fps_count = int(round(cnt / grabtime))
                print('Camera %i collected %i frames at %i fps.' % (n_cam, cnt, fps_count))
        # Else wait for next frame available
        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            time.sleep(0.0001)
        except Exception as e:
            logging.error('Caught exception: {}'.format(e))


def CloseCamera(cam_params, camera, grabdata):
    n_cam = cam_params["n_cam"]

    print('Closing camera {}... Please wait.'.format(n_cam+1))
    # Close FLIR camera after acquisition stops
    while True:
        try:
            try:
                SaveMetadata(cam_params,grabdata)
                time.sleep(1)
                camera.Close()
                camera.StopGrabbing()
                break
            except:
                time.sleep(0.1)
        except KeyboardInterrupt:
            break