# !/usr/bin/env python3
# Author: Shane Harrell

import json
import sys
from datetime import datetime
import redis
import asyncio
import requests
import dotenv
import os

dotenv.load_dotenv()

# Import version for User-Agent
from busylight_app import APP_VERSION

# Busylight
from busylight.lights import Busylight_Omega
from busylight.lights.kuando._busylight import Ring, Instruction, CommandBuffer

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

redis_bearer_token = os.getenv('REDIS_BEARER_TOKEN')
if not redis_bearer_token:
    print (f"[{get_timestamp()}] Error: REDIS_BEARER_TOKEN is not set")
    sys.exit(1)

light = Busylight_Omega.first_light()

def get_redis_password():
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {redis_bearer_token}',
        'User-Agent': f'BusylightController/{APP_VERSION}'
    }
    r = requests.get(f'http://{redis_host}/api/status/redis-info', headers=headers)
    try:
        return json.loads(r.text)['password']
    except:
        error = json.loads(r.text)
        print (f"[{get_timestamp()}] Error getting redis password: {error['error']}")
        sys.exit(1)

async def check_light_status():
    while True:
        try:
            current_color = light.color
            await asyncio.sleep(10)
        except Exception as e:
            print (f"Error checking light status: {e}")
            await asyncio.sleep(10)

async def redis_listener(redis_client):
    queue_name = "event_queue"  # historical state of the queue
    queue_channel = "event_channel" # real time events channel

    # Get the most recent status from redis on startup in case of crash or shutdown
    try:
        latest = redis_client.lindex(queue_name, -1)
        if latest:
            data = json.loads(latest)
            print (f"[{get_timestamp()}] Last message: {data}")
            status = data['status']
            light_control(status)
        else:
            light_control('normal')
    except Exception as e:
        print (f"Error getting last message: {e}")
    
    pubsub = redis_client.pubsub()
    pubsub.subscribe(queue_channel)
    print(f"[{get_timestamp()}] Subscribed to {queue_channel}")

    print(f"[{get_timestamp()}] Listening for messages...")
    while True:
        message = pubsub.get_message()
        if message and message["type"] == "message":
            data = json.loads(message["data"])
            print(f"[{get_timestamp()}] Received: {data}")
    
            try:
                status = data['status']
            except:
                print(f'[{get_timestamp()}] Invalid JSON response from the api')
                status = 'error'

            light_control(status)
        await asyncio.sleep(0.1)  # Small sleep to prevent CPU hogging

def light_control(status: str) -> None:
    current_color = light.color

    COLOR_MAP = {
        'alert': (255,0,0),
        'alert-acked': (255, 140, 0),
        'warning': (255, 255, 0),
        'error': (255, 0, 255),
        'default': (0, 255, 0), # Normal
        'off': (0, 0, 0)        # Off
    }

    COLOR_NAMES = {
        (255, 0, 0): "Red (Alert)",
        (255, 140, 0): "Orange (Alert-Acked)",
        (255, 255, 0): "Yellow (Warning)",
        (255, 0, 255): "Purple (Error)",
        (0, 255, 0): "Green (Normal)",
        (0, 0, 0): "Off"
    }

    # Defaults
    ringtone = Ring.Off
    volume = 0
    color = COLOR_MAP.get(status, COLOR_MAP['default'])
    
    if color != current_color:
        print (f"[{get_timestamp()}] Changing color from {COLOR_NAMES[current_color]} to {COLOR_NAMES[color]}")

    if status == 'alert':
        ringtone = Ring.OpenOffice
        volume = 7
    
    try:
        cmd_buffer = CommandBuffer()

        # Create and send the instructions to the light
        instruction = Instruction.Jump(
            ringtone=ringtone,
            volume=volume,
            update=1,
        )

        cmd_buffer.line0 = instruction.value
        command_bytes = bytes(cmd_buffer)

        light.write_strategy(command_bytes)
        light.on(color)
        light.update()

    except Exception as e:
        print (f"Error controlling light: {e}")


redis_host = 'busylight.signalwire.me'
redis_port = 6379
redis_password = get_redis_password()

async def main():
    tasks = []
    try:
        print(f"[{get_timestamp()}] Starting up {light.name}")

        redis_client = redis.StrictRedis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=0,
            decode_responses=True            
        )

        # Add a try catch to check if the redis connection is successful
        redis_client.ping()
        print(f"[{get_timestamp()}] Connected to Redis successfully")

        tasks = [
            asyncio.create_task(check_light_status()),
            asyncio.create_task(redis_listener(redis_client))
        ]

        await asyncio.gather(*tasks)

    except asyncio.CancelledError:
        print(f"\n[{get_timestamp()}] Shutting down...")
        light_control('off')
        print(f"\n[{get_timestamp()}] Light and ringer turned off.\n\nGoodbye!")
        raise  # Re-raise the CancelledError to properly shut down


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # The KeyboardInterrupt is caught here after the tasks are properly cancelled
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
