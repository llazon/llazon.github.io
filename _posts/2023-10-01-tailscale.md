---
layout: post
title:  "Using Tailscale to access your AWS resources"
date: 2023-10-01 00:00:00 -0000
categories: 
---

# Overview
Tailscale is a next generation VPN solution. Tailscale can be used to access internal resources and/or route traffic through an exit node for use in public spaces. Access to Tailscale is managed through Google Workspaces in this example.

# Tailscale
## ACLs
## Auth Keys

# AWS EC2

# AWS ECS

# Client

## Download and install

Download and install from here for both desktop/laptop and android/ios:

https://tailscale.com/download/ [https://tailscale.com/download/]


## Log in

Note: disconnect from Tunnelblick/Viscosity before connecting with Tailscale to avoid any conflicts.

 * Click Log in from the Tailscale menu bar.
   

 * Submit your email address and you will be redirected to Google Workspaces in order to authenticate.


Accessing resources

    * ssh access can be done in two ways:
       * via the subnet routers using
         dns names
       * via direct access using the tailnet name such as
         or IP addresses. You can copy these addresses from the Tailscale menu by clicking on the name in this list:
         
   


Using Exit Nodes

We run a set of exit nodes in various geographic locations which you can optionally activate from the Tailscale menu. These serve the same purpose as the "VPN All" profiles on the legacy VPN solution, they will route all of your internet traffic out via that location. This can be used if you need to view the site from a different geography, or if you are on an untrusted wifi network and wish to add an extra layer of protection. Note that unlike something like cloak, this will not prevent direct network access from your device onto the local network, and like the old "VPN All" profiles, it does not replace a firewall, you should still be using the firewall built into your operating system.


Links

 * https://tailscale.com/ [https://tailscale.com/]
 * https://tailscale.com/kb/start [https://tailscale.com/kb/start]
 * https://www.wireguard.com/ [https://www.wireguard.com/]





Troubleshooting

