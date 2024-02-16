from pysnmp.hlapi import *


import os


iterator = getCmd(
    SnmpEngine(),
    CommunityData('public', mpModel=0),
    UdpTransportTarget(('127.0.0.1', 161)),
    ContextData(),
    ObjectType(ObjectIdentity('1.3.6.1.2.1.25.1.1.0'))
)

errorIndication, errorStatus, errorIndex, varBinds = next(iterator)


if errorIndication:
    print(errorIndication)

elif errorStatus:
    print('%s at %s' % (errorStatus.prettyPrint(),
                        errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))

else:
    for varBind in varBinds:
        print(' = '.join([x.prettyPrint() for x in varBind]))
