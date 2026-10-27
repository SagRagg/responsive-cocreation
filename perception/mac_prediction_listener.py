#!/usr/bin/env python3

import argparse
import time

import roslibpy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()

    ros = roslibpy.Ros(host=args.host, port=args.port)

    topic = roslibpy.Topic(
        ros,
        "/digit_prediction",
        "std_msgs/msg/Int32"
    )

    def callback(message):
        print(f"Received CNN prediction: {message['data']}")

    print(f"Connecting to ws://{args.host}:{args.port}")
    ros.run()

    print("Connected. Listening on /digit_prediction...")
    topic.subscribe(callback)

    try:
        while ros.is_connected:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        topic.unsubscribe()
        ros.terminate()


if __name__ == "__main__":
    main()
