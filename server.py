#!/usr/bin/env python3
import socket
import struct
import random

HOST = "0.0.0.0"
PORT = 54541

# Message Types (16-bit fields)
MSG_SUBSCRIBE    = 0  # Subscription Request
MSG_INFO_REQUEST = 1  # Server’s request for information
MSG_SEND_NAME    = 2  # Client’s Full Name
MSG_SEND_PHONE   = 3  # Client’s Phone Number
MSG_SEND_ADDRESS = 4  # Client’s Address
MSG_TERMINATE    = 5  # Termination Message

# Information Types (for Info Request payload, 16-bit)
INFO_FULL_NAME = 0
INFO_PHONE     = 1
INFO_ADDRESS   = 2
INFO_RESEND    = 3

# Termination Codes (examples):
#   0 = "All went well"
#   1 = "AM inconsistent"
#   2 = "Unknown Information Type"
#   3 = "Phone Number incorrect or missing"
#   4 = "Full Name missing (or first name)"
#   5 = "Last Name missing"
#   6 = "Both First and Last Name missing"
#   7 = "Postal Code missing or invalid"
#   8 = "Postal Address missing"
#   9 = "Postal Country missing"
#  12 = "City missing" (or combined address error)
#  13 = "All postal data missing"

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return data

# Helper to receive number of bytes
def receive_header(sock):
    raw = recv_all(sock, 8)
    if not raw:
        return None, None, None
    msg_type, am, length = struct.unpack("!HHI", raw)
    return msg_type, am, length

#termination message with notification code

def send_msg(sock, msg_type, am, length, payload=b""):
    header = struct.pack("!HHI", msg_type, am, length)
    sock.sendall(header + payload)

# Send request for specific info type 

def send_info_request(sock, info_type, am):
    payload = struct.pack("!H", info_type)
    send_msg(sock, MSG_INFO_REQUEST, am, 8, payload)
    # For debugging, print which info type is requested.
    if info_type == INFO_FULL_NAME:
        print("[SERVER] Requesting: Full Name")
    elif info_type == INFO_PHONE:
        print("[SERVER] Requesting: Phone Number")
    elif info_type == INFO_ADDRESS:
        print("[SERVER] Requesting: Address")
    elif info_type == INFO_RESEND:
        print("[SERVER] Requesting: Resend previous")

# Validates phone number format

def send_termination(sock, am, notif_code):
    payload = struct.pack("!H", notif_code)
    send_msg(sock, MSG_TERMINATE, am, 8, payload)
    print(f"[SERVER] Sent termination with code {notif_code}")
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception as e:
        print(f"[SERVER] Shutdown error: {e}")

# Validates TK

def handle_client(conn):
    # Step 1: Receive Subscription Request.
    msg_type, client_am, length = receive_header(conn)
    if msg_type != MSG_SUBSCRIBE or length != 8:
        send_termination(conn, 0, 2)
        conn.close()
        return
    print(f"[SERVER] Received subscription from AM: {client_am}")

    # Step 2: Process required fields in random order.
    info_list = [INFO_FULL_NAME, INFO_PHONE, INFO_ADDRESS]
    random.shuffle(info_list)
    received = {"name": False, "phone": False, "address": False}

    # For each field, loop until accepted.
    for field in info_list:
        field_accepted = False
        first_response = None
        while not field_accepted:
            request_type = field if first_response is None else INFO_RESEND
            send_info_request(conn, request_type, client_am)
            resp_type, am_resp, resp_length = receive_header(conn)
            if am_resp != client_am:
                send_termination(conn, client_am, 1)
                conn.close()
                return
            payload = recv_all(conn, resp_length - 8)
            if payload is None:
                conn.close()
                return
            if request_type == INFO_RESEND:
                if payload != first_response:
                    send_termination(conn, client_am, 2)
                    conn.close()
                    return
                print("[SERVER] Resent payload accepted.")
                field_accepted = True
            else:
                first_response = payload
                if field == INFO_FULL_NAME:
                    if resp_type != MSG_SEND_NAME or len(payload) < 4:
                        send_termination(conn, client_am, 2)
                        conn.close()
                        return
                    fn_len = struct.unpack("!H", payload[0:2])[0]
                    offset = 4
                    if len(payload) < offset + fn_len:
                        send_termination(conn, client_am, 4)
                        conn.close()
                        return
                    first_name = payload[offset:offset+fn_len].decode("utf-8")
                    offset += fn_len
                    pad = (4 - (fn_len % 4)) % 4
                    offset += pad
                    if len(payload) < offset + 4:
                        send_termination(conn, client_am, 5)
                        conn.close()
                        return
                    ln_len = struct.unpack("!H", payload[offset:offset+2])[0]
                    offset += 4
                    if len(payload) < offset + ln_len:
                        send_termination(conn, client_am, 5)
                        conn.close()
                        return
                    last_name = payload[offset:offset+ln_len].decode("utf-8")
                    if fn_len == 0 and ln_len == 0:
                        send_termination(conn, client_am, 6)
                        conn.close()
                        return
                    if fn_len == 0:
                        send_termination(conn, client_am, 4)
                        conn.close()
                        return
                    if ln_len == 0:
                        send_termination(conn, client_am, 5)
                        conn.close()
                        return
                    received["name"] = True
                    print(f"[SERVER] Received Name: {first_name} {last_name}")
                    field_accepted = True

                elif field == INFO_PHONE:
                    if resp_type != MSG_SEND_PHONE or len(payload) < 12:
                        send_termination(conn, client_am, 3)
                        conn.close()
                        return
                    phone = payload[:10].decode("utf-8")
                    if len(phone) != 10 or phone[0] not in ('2', '6') or not phone.isdigit():
                        send_termination(conn, client_am, 3)
                        conn.close()
                        return
                    received["phone"] = True
                    print(f"[SERVER] Received Phone: {phone}")
                    field_accepted = True

                elif field == INFO_ADDRESS:
                    if resp_type != MSG_SEND_ADDRESS or len(payload) < 8:
                        send_termination(conn, client_am, 7)
                        conn.close()
                        return
                    tk = struct.unpack("!H", payload[0:2])[0]
                    country = payload[2:4].decode("utf-8")
                    street_len = struct.unpack("!H", payload[4:6])[0]
                    offset = 8
                    if len(payload) < offset + street_len:
                        send_termination(conn, client_am, 8)
                        conn.close()
                        return
                    street = payload[offset:offset+street_len].decode("utf-8")
                    offset += street_len
                    pad = (4 - (street_len % 4)) % 4
                    offset += pad
                    if len(payload) < offset + 4:
                        send_termination(conn, client_am, 12)
                        conn.close()
                        return
                    city_len = struct.unpack("!H", payload[offset:offset+2])[0]
                    offset += 4
                    if len(payload) < offset + city_len:
                        send_termination(conn, client_am, 12)
                        conn.close()
                        return
                    city = payload[offset:offset+city_len].decode("utf-8")
                    if tk < 10000 or tk > 65000:
                        send_termination(conn, client_am, 7)
                        conn.close()
                        return
                    if len(country) != 2:
                        send_termination(conn, client_am, 9)
                        conn.close()
                        return
                    if street_len == 0 and city_len == 0:
                        send_termination(conn, client_am, 13)
                        conn.close()
                        return
                    elif street_len == 0:
                        send_termination(conn, client_am, 8)
                        conn.close()
                        return
                    elif city_len == 0:
                        send_termination(conn, client_am, 12)
                        conn.close()
                        return
                    received["address"] = True
                    print(f"[SERVER] Received Address: {tk}, {country}, {street}, {city}")
                    field_accepted = True

                else:
                    send_termination(conn, client_am, 2)
                    conn.close()
                    return
    # Final Step: If all fields received, send termination code 0; otherwise, send error.
    if received["name"] and received["phone"] and received["address"]:
        send_termination(conn, client_am, 0)
        print(f"[SERVER] All information received successfully from AM {client_am}.")
    else:
        error_code = 2
        if not received["name"]:
            error_code = 4
        elif not received["phone"]:
            error_code = 3
        elif not received["address"]:
            error_code = 7
        send_termination(conn, client_am, error_code)
        print(f"[SERVER] Termination sent with error code {error_code} for AM {client_am}.")
    conn.close()

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[SERVER] Listening on port {PORT}...")
        while True:
            conn, addr = s.accept()
            print(f"[SERVER] Connection from {addr}")
            try:
                handle_client(conn)
            except Exception as e:
                print(f"[SERVER] Exception: {e}")
                conn.close()

if __name__ == "__main__":
    start_server()
