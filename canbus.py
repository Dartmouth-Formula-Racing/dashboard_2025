# Worker process for handling CAN data
# CAN interface is MCP25625 (Combined MCP2515 controller and MCP2551 transceiver)
# Received data is sent to the main process via a queue
# Data to be sent is received from the main process via a queue

# Useful documentation:
# https://python-can.readthedocs.io/en/stable/interfaces/socketcand.html
# https://python-can.readthedocs.io/en/stable/message.html
# https://forum.peak-system.com/viewtopic.php?t=1267

import config
import time
from os import system

if config.IN_CAR:
    import can
    import RPi.GPIO as GPIO

# Queues are passed to the worker process from the main process
rx_queue = None
tx_queue = None

# State dictionary is passed to the worker process from the main process
state = None

# CAN bus instance
bus = None

def build_button_message(drive_pressed, neutral_pressed, reverse_pressed):
    state = 0
    if reverse_pressed:
        state = 2
    if drive_pressed:
        state = 1
    if neutral_pressed:
        state = 0
    data = [state]
    dlc = len(data)
    return can.Message(arbitration_id=config.CAN_BASE_ID, data=data, dlc=dlc, is_extended_id=config.CAN_EXTENDED_ID)

def run(_rx_queue, _tx_queue, _state):
    global rx_queue
    global tx_queue
    global state
    global bus

    rx_queue = _rx_queue
    tx_queue = _tx_queue
    state = _state

    # Set nRST high and STBY low
    GPIO.output(config.CAN_NRST_GPIO, GPIO.HIGH)
    GPIO.output(config.CAN_STBY_GPIO, GPIO.LOW)
    # Start CAN interface
    system("sudo ip link set can0 up type can bitrate 500000 triple-sampling on restart-ms 100")
    system("sudo ifconfig can0 txqueuelen 1000")

    # Main loop
    while True:
        # Initialize socketcan interface
        while bus is None:
            try:
                bus = can.interface.Bus(bustype='socketcan', channel='can0')
                state['canconnected'] = True
            except:  # noqa: E722
                bus = None
                state['canconnected'] = False
                print("CAN initialization failed, retrying...")
                time.sleep(0.5)

        # Check if bus is in error state
        if bus.state == can.BusState.ERROR:
            print("CAN bus is in error state")
            bus = None
            state['canconnected'] = False
            continue

        # Check for received data
        received = bus.recv(timeout=config.CAN_RECV_TIMEOUT)
        if (received is not None):
            rx_queue.put(received)

        # Check for data to send
        while not tx_queue.empty():
            msg = tx_queue.get()
            bus.send(msg)