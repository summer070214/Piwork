#开启串口并且发送AT指令
#复制到树莓派中

#安装依赖库
#sudo apt update
#sudo apt install python3-serial -y
# 或者使用 pip：
# pip install pyserial
import glob
import re
import serial
import time

#打开串口
def find_at_port():
  # 1. 查找所有匹配的串口设备
  ports = glob.glob('/dev/ttyUSB*')
  ports.sort()

  if not ports:
    print('❌ 未找到任何 /dev/ttyUSB* 设备，请检查模块连接及驱动。')
    return None

  print(f'🔍 发现以下串口设备: {ports}')

  # 2. 遍历每个串口进行测试
  for port in ports:
    print(f'👉 正在测试串口: {port} ...')
    try:
      with serial.Serial(port, baudrate=115200, timeout=1) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 发送 AT 指令
        ser.write(b'AT\r\n')
        time.sleep(0.5)

        response = ser.read_all().decode('utf-8', errors='ignore')
        print(f'   [接收响应]: {repr(response)}')

        # 检查是否包含 OK，一旦找到就直接进入后续流程
        if 'OK' in response:
          print(f'✅ 成功找到 AT 端口: {port}')

          # ==================== 后续业务逻辑（基于流程图）====================
          print('\n--- 开始执行模组后续初始化流程 ---')

          # 步骤 A：查询 SIM 卡状态 (AT+CPIN?)，限时 20 秒
          sim_ready = False
          for _ in range(10):
            ser.write(b'AT+CPIN?\r\n')
            time.sleep(2)
            cpin_resp = ser.read_all().decode('utf-8', errors='ignore')
            print(f'   [AT+CPIN? 响应]: {cpin_resp.strip()}')
            if 'READY' in cpin_resp or '+CPIN:' in cpin_resp:
              print('✅ (U)SIM 卡状态识别成功')
              sim_ready = True
              break
          if not sim_ready:
            print(
                '❌ 20秒内无法识别 (U)SIM 卡状态，建议重启模块或检查 SIM 卡！'
            )
            return port

          # 步骤 B：查询 PS 业务状态 (AT+C5GREG?)，限时 60 秒
          ps_registered = False
          for _ in range(20):
            ser.write(b'AT+C5GREG?\r\n')
            time.sleep(3)
            reg_resp = ser.read_all().decode('utf-8', errors='ignore')
            print(f'   [AT+C5GREG? 响应]: {reg_resp.strip()}')

            match = re.search(r'\+C5GREG:\s*\d+,\s*(\d+)', reg_resp)
            if match and int(match.group(1)) in [1, 5]:
              print(
                  f'✅ 模块已在 5GS 网络注册上 PS 业务 (<stat>={match.group(1)})'
              )
              ps_registered = True
              break

          # 如果 60 秒内未成功注册 PS 业务，执行重置恢复流程
          if not ps_registered:
            print('⚠️ 未能在规定时间内注册 PS 业务，执行重置恢复流程...')
            ser.write(b'AT+CGDCONT=1,"IP","internet"\r\n')
            time.sleep(1)
            ser.write(b'AT+CFUN=0\r\n')  # 关闭射频
            time.sleep(2)
            ser.write(b'AT+CFUN=1\r\n')  # 开启射频
            time.sleep(5)
            print('   -> 射频重启完毕')

          # =================================================================

          return port
    except Exception as e:
      print(f'   ⚠️ 无法访问 {port} (可能被占用或权限不足): {e}')

  print('❌ 遍历结束，未能在任何串口上收到 OK 响应。')
  return None


if __name__ == '__main__':
  found_port = find_at_port()
  if found_port:
    print(f'\n🎉 最终锁定的可用 AT 串口为: {found_port}')

#链接公网
def connect_to_network(port, max_retries=3):
    print(f"🚀 正在通过串口 {port} 配置、激活并建立 Socket 连接...")
    
    try:
        with serial.Serial(port, baudrate=115200, timeout=5) as ser:
            ser.reset_input_buffer()
            
            # --- 外层大循环：如果 AT+QIOPEN 失败或 150s 超时，整个流程从配网重新开始 ---
            for retry in range(1, max_retries + 1):
                print(f"\n--- [完整配网流程 - 第 {retry}/{max_retries} 次尝试] ---")
                
                # 1. 配置 PDP 上下文 (以中国联通 UNINET 为例，可根据实际修改)
                print("步骤 1: 配置 PDP 上下文 (AT+QICSGP)...")
                ser.write(b'AT+QICSGP=1,1,"UNINET","",0\r\n')
                time.sleep(1)
                res1 = ser.read_all().decode('utf-8', errors='ignore')
                print(res1)
                if 'OK' not in res1:
                    print("❌ PDP 上下文配置失败，准备重试...")
                    continue

                # 2. 循环尝试激活 PDP 上下文（带有失败去激活和内部重试机制）
                print("步骤 2: 循环尝试激活 PDP 上下文 (AT+QIACT)...")
                activation_success = False
                
                for act_attempt in range(1, 4):  # 激活内部最多尝试 3 次
                    print(f"   -> 激活尝试 {act_attempt}/3 (AT+QIACT=1)...")
                    ser.write(b'AT+QIACT=1\r\n')
                    time.sleep(5)  # 等待网络激活响应
                    res2 = ser.read_all().decode('utf-8', errors='ignore')
                    print(res2)
                    
                    if 'OK' in res2:
                        print("   ✅ PDP 上下文激活成功！")
                        activation_success = True
                        break
                    else:
                        print("   ⚠️ 激活未收到 OK，执行去激活补救 (AT+QIDEACT)...")
                        ser.write(b'AT+QIDEACT=1\r\n')
                        time.sleep(3)
                        ser.read_all()
                
                # 如果内部激活 3 次均失败，则跳出到外层，重新走一遍配置和激活
                if not activation_success:
                    print("❌ 激活 PDP 上下文连续失败，准备重新配网...")
                    continue

                # 3. 查询 IP 地址确认联通
                print("步骤 3: 查询网络 IP 地址 (AT+QIACT?)...")
                ser.write(b'AT+QIACT?\r\n')
                time.sleep(1)
                res3 = ser.read_all().decode('utf-8', errors='ignore')
                print(res3)

                # 4. 打开 Socket 服务 (AT+QIOPEN)
                # 参数说明: contextID=1, connectID=0, service_type="TCP", address="220.180.239.212"(示例IP), port=80, local_port=0, access_mode=0(缓存模式)
                print("步骤 4: 打开 Socket 连接 (AT+QIOPEN)...")
                ser.reset_input_buffer()
                ser.write(b'AT+QIOPEN=1,0,"TCP","47.110.132.201",22,0,0\r\n')
                
                qiopen_success = False
                start_time = time.time()
                
                # 官方要求：等待 +QIOPEN 响应最长可达 150 秒[cite: 10, 27]
                while time.time() - start_time < 150:
                    if ser.in_waiting > 0:
                        chunk = ser.read_all().decode('utf-8', errors='ignore')
                        print(chunk, end="")
                        
                        # 检查是否成功收到 +QIOPEN: 0,0 结果
                        if 'OK' in chunk and '+QIOPEN: 0,0' in chunk:
                            qiopen_success = True
                            break
                        elif '+QIOPEN:' in chunk and '+QIOPEN: 0,0' not in chunk:
                            # 收到错误的结果码
                            break
                    time.sleep(1)

                if qiopen_success:
                    print("\n🎉 AT+QIOPEN 打开连接成功，模组已成功连上公网并建立 Socket！")
                    return True
                else:
                    print("\n⚠️ 150 秒内未收到成功的 +QIOPEN 响应或打开失败，执行 AT+QICLOSE 关闭连接...")
                    # 官方要求：150 秒内无响应需通过 AT+QICLOSE 关闭 Socket[cite: 10, 27]
                    ser.write(b'AT+QICLOSE=0\r\n')
                    time.sleep(2)
                    ser.read_all()
                    
                    # 同时去激活上下文，准备进入外层循环重新配网
                    ser.write(b'AT+QIDEACT=1\r\n')
                    time.sleep(2)
                    ser.read_all()
            
            print(f"\n❌ 连续 {max_retries} 次完整流程均失败，建议按照官方规范重启模组。")
            return False
            
    except Exception as e:
        print(f"⚠️ 执行出错: {e}")
        
    return False


if __name__ == '__main__':
    # 如果提示权限不足，请使用 sudo 运行脚本
    found_port = find_at_port()
    if found_port:
        print(f"\n🎉 最终锁定的可用 AT 串口为: {found_port}")
        connect_to_network(found_port)
#运行代码sudo python3 AT.py