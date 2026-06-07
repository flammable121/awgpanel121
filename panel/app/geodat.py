from __future__ import annotations

import ipaddress
from typing import Iterable

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def _get_message_class(pool: descriptor_pool.DescriptorPool, list_name: str) -> type:
    desc = pool.FindMessageTypeByName(list_name)

    # protobuf >= 5 provides module-level GetMessageClass
    if hasattr(message_factory, "GetMessageClass"):
        try:
            return message_factory.GetMessageClass(desc)
        except Exception:
            pass

    factory = message_factory.MessageFactory(pool)
    if hasattr(factory, "GetPrototype"):
        return factory.GetPrototype(desc)
    if hasattr(factory, "GetMessageClass"):
        return factory.GetMessageClass(desc)

    raise RuntimeError("Unsupported protobuf runtime")


def _build_list_message(list_name: str, item_name: str) -> type:
    file_desc = descriptor_pb2.FileDescriptorProto()
    file_desc.name = f"{list_name.lower()}.proto"
    file_desc.syntax = "proto3"

    cidr_msg = file_desc.message_type.add()
    cidr_msg.name = "CIDR"
    cidr_ip = cidr_msg.field.add()
    cidr_ip.name = "ip"
    cidr_ip.number = 1
    cidr_ip.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    cidr_ip.type = descriptor_pb2.FieldDescriptorProto.TYPE_BYTES
    cidr_prefix = cidr_msg.field.add()
    cidr_prefix.name = "prefix"
    cidr_prefix.number = 2
    cidr_prefix.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    cidr_prefix.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT32

    item_msg = file_desc.message_type.add()
    item_msg.name = item_name
    item_field = item_msg.field.add()
    item_field.name = "country_code"
    item_field.number = 1
    item_field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    item_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    if item_name == "GeoIP":
        cidr_field = item_msg.field.add()
        cidr_field.name = "cidr"
        cidr_field.number = 2
        cidr_field.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
        cidr_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        cidr_field.type_name = ".CIDR"

    list_msg = file_desc.message_type.add()
    list_msg.name = list_name
    list_field = list_msg.field.add()
    list_field.name = "entry"
    list_field.number = 1
    list_field.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    list_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    list_field.type_name = f".{item_name}"

    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(file_desc.SerializeToString())
    return _get_message_class(pool, list_name)


def _extract_codes(entries: Iterable) -> list[str]:
    values = {entry.country_code for entry in entries if getattr(entry, "country_code", "")}
    return sorted(values)


_GeoIPList = _build_list_message("GeoIPList", "GeoIP")
_GeoSiteList = _build_list_message("GeoSiteList", "GeoSite")


def load_geoip_tags(path: str) -> list[str]:
    with open(path, "rb") as fh:
        data = fh.read()
    message = _GeoIPList.FromString(data)
    return _extract_codes(message.entry)


def load_geoip_cidrs(path: str, tags: Iterable[str]) -> tuple[list[str], list[str]]:
    selected = {tag.strip().lower() for tag in tags if tag and tag.strip()}
    if not selected:
        return [], []

    with open(path, "rb") as fh:
        data = fh.read()
    message = _GeoIPList.FromString(data)

    v4: set[str] = set()
    v6: set[str] = set()
    for entry in message.entry:
        code = getattr(entry, "country_code", "").lower()
        if code not in selected:
            continue
        for cidr in getattr(entry, "cidr", []):
            raw_ip = bytes(getattr(cidr, "ip", b""))
            prefix = int(getattr(cidr, "prefix", 0))
            try:
                if len(raw_ip) == 4:
                    network = ipaddress.ip_network((ipaddress.IPv4Address(raw_ip), prefix), strict=False)
                    v4.add(str(network))
                elif len(raw_ip) == 16:
                    network = ipaddress.ip_network((ipaddress.IPv6Address(raw_ip), prefix), strict=False)
                    v6.add(str(network))
            except ValueError:
                continue
    return sorted(v4, key=lambda item: ipaddress.ip_network(item)), sorted(v6, key=lambda item: ipaddress.ip_network(item))


def load_geosite_tags(path: str) -> list[str]:
    with open(path, "rb") as fh:
        data = fh.read()
    message = _GeoSiteList.FromString(data)
    return _extract_codes(message.entry)
