#!/usr/bin/env python3
import socket
import struct

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 54541

# Message Types
MSG_SUBSCRIBE    = 0  # Subscription request
MSG_INFO_REQUEST = 1  # Server request for information
MSG_SEND_NAME    = 2  # Full name message
MSG_SEND_PHONE   = 3  # Phone number message
MSG_SEND_ADDRESS = 4  # Address message
MSG_TERMINATE    = 5  # Termination message

# Information Types (for Info Request payload)
INFO_FULL_NAME = 0
INFO_PHONE     = 1
INFO_ADDRESS   = 2
INFO_RESEND    = 3

#receive `length` in bytes

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        more = sock.recv(length - len(data))
        if not more:
            raise EOFError("Connection closed unexpectedly")
        data += more
    return data

#Sends initial subscription request

def send_subscription(sock, am):
    msg_type = MSG_SUBSCRIBE
    length = 8
    header = struct.pack("!HHI", msg_type, am, length)
    sock.sendall(header)
    print(f"[CLIENT] Sent subscription with AM: {am}")


# Constructs and returns a binary essage with full name

def build_full_name_message(am, first_name, last_name):
    msg_type = MSG_SEND_NAME
    fn_bytes = first_name.encode("utf-8")
    ln_bytes = last_name.encode("utf-8")
    fn_len = len(fn_bytes)
    ln_len = len(ln_bytes)
    fn_pad = (4 - (fn_len % 4)) % 4
    ln_pad = (4 - (ln_len % 4)) % 4
    total_length = 8 + 4 + fn_len + fn_pad + 4 + ln_len + ln_pad
    header = struct.pack("!HHIHH", msg_type, am, total_length, fn_len, 0)
    payload = fn_bytes + (b'\x00' * fn_pad) + struct.pack("!HH", ln_len, 0) + ln_bytes + (b'\x00' * ln_pad)
    return header + payload


# Constructs a binary message containing full phone number

def build_phone_message(am, phone):
    msg_type = MSG_SEND_PHONE
    # Truncate (or validate) the phone string to 10 digits.
    phone = phone[:10]
    # Set the length field to 20, so that header (8 bytes) + payload (12 bytes) = 20 bytes total.
    header = struct.pack("!HHI", msg_type, am, 20)
    # Pack phone as 10 bytes, plus 2 bytes of zero padding.
    payload = struct.pack("!10sH", phone.encode("utf-8"), 0)
    return header + payload


# Constructs a binary message containing full postal address

def build_address_message(am, tk, country, street, city):
    msg_type = MSG_SEND_ADDRESS
    street_bytes = street.encode("utf-8")
    city_bytes = city.encode("utf-8")
    street_len = len(street_bytes)
    city_len = len(city_bytes)
    street_pad = (4 - (street_len % 4)) % 4
    city_pad = (4 - (city_len % 4)) % 4
    total_length = 8 + 2 + 2 + 2 + 2 + street_len + street_pad + 2 + 2 + city_len + city_pad
    header = struct.pack("!HHI", msg_type, am, total_length)
    payload = struct.pack("!H2sHH", tk, country.encode("utf-8"), street_len, 0)
    payload += street_bytes + (b'\x00' * street_pad)
    payload += struct.pack("!HH", city_len, 0)
    payload += city_bytes + (b'\x00' * city_pad)
    return header + payload

# Handles termination

def handle_termination(sock):
    try:
        raw = recv_all(sock, 8)
    except (EOFError, ConnectionResetError):
        print("[CLIENT] Connection closed by server during termination.")
        return
    msg_type, am, length = struct.unpack("!HHI", raw)
    if msg_type == MSG_TERMINATE:
        try:
            notif = struct.unpack("!H", recv_all(sock, 2))[0]
        except (EOFError, ConnectionResetError):
            print("[CLIENT] Termination payload not received; connection closed.")
            return
        if notif == 0:
            print("[CLIENT] ✅ Subscription successful!")
        else:
            print(f"[CLIENT] ❌ Terminated with error code: {notif}")
    else:
        print("[CLIENT] Unexpected message received.")
    sock.close()

def main():
    am = int(input("Enter your Academic ID (5 digits): "))
    cached = {}   # Store user responses when first input.
    last_sent = None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((SERVER_HOST, SERVER_PORT))
        print("[CLIENT] Connected to server.")
        send_subscription(sock, am)

        while True:
            try:
                header = recv_all(sock, 8)
            except (EOFError, ConnectionResetError):
                print("[CLIENT] Connection closed by server.")
                break

            msg_type, server_am, length = struct.unpack("!HHI", header)
            if msg_type == MSG_INFO_REQUEST:
                info_type = struct.unpack("!H", recv_all(sock, 2))[0]

                if info_type == INFO_FULL_NAME:
                    if "name" not in cached:
                        first_name = input("Enter your First Name: ")
                        last_name = input("Enter your Last Name: ")
                        cached["name"] = (first_name, last_name)
                    message = build_full_name_message(am, *cached["name"])
                    last_sent = ("name", message)
                    sock.sendall(message)
                    print("[CLIENT] Sent Full Name.")

                elif info_type == INFO_PHONE:
                    if "phone" not in cached:
                        phone = input("Enter your Phone Number (10 digits, starting with 2 or 6): ")
                        cached["phone"] = phone
                    message = build_phone_message(am, cached["phone"])
                    last_sent = ("phone", message)
                    sock.sendall(message)
                    print("[CLIENT] Sent Phone Number.")

                elif info_type == INFO_ADDRESS:
                    if "address" not in cached:
                        tk = int(input("Enter your Postal Code (10000-65000): "))
                        street = input("Enter your Street Address: ")
                        city = input("Enter your City: ")
                        country = input("Enter your Country Code (2 letters): ")
                        cached["address"] = (tk, country, street, city)
                    message = build_address_message(am, *cached["address"])
                    last_sent = ("address", message)
                    sock.sendall(message)
                    print("[CLIENT] Sent Address.")

                elif info_type == INFO_RESEND:
                    print("[CLIENT] 🔁 Resend requested.")
                    if last_sent:
                        sock.sendall(last_sent[1])
                        print("[CLIENT] Resent last message.")
                    else:
                        print("[CLIENT] Nothing available to resend.")
                else:
                    print("[CLIENT] Unknown Information Type received. Terminating.")
                    break

            elif msg_type == MSG_TERMINATE:
                handle_termination(sock)
                break
            else:
                print("[CLIENT] Received unexpected message type; terminating.")
                break

if __name__ == "__main__":
    main()
