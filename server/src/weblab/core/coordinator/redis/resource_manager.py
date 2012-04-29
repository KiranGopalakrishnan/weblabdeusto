#!/usr/bin/env python
#-*-*- encoding: utf-8 -*-*-
#
# Copyright (C) 2005 onwards University of Deusto
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of contributions made by many individuals,
# listed below:
#
# Author: Pablo Orduña <pablo@ordunya.com>
#

import json
from sqlalchemy.orm.exc import StaleDataError

from weblab.data.experiments import ExperimentId, ExperimentInstanceId
from weblab.core.coordinator.resource import Resource
import weblab.core.coordinator.exc as CoordExc

from voodoo.typechecker import typecheck


WEBLAB_EXPERIMENT_TYPES              = "weblab:experiment_types"
WEBLAB_EXPERIMENT_RESOURCES          = "weblab:experiment_types:%s:resource_types"
WEBLAB_EXPERIMENT_INSTANCES          = "weblab:experiment_types:%s:instances"
WEBLAB_EXPERIMENT_INSTANCE           = "weblab:experiment_types:%s:instances:%s"

WEBLAB_RESOURCES                     = "weblab:resources"
WEBLAB_RESOURCE                      = "weblab:resources:%s"
WEBLAB_RESOURCE_EXPERIMENTS          = "weblab:resources:%s:experiment_types"
WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS = "weblab:resources:%s:%s:experiment_instances"

WEBLAB_RESERVATIONS_ACTIVE_SCHEDULERS = "weblab:reservations:%s:active_schedulers"

LAB_COORD       = "laboratory_coord_address"
RESOURCE_INST   = "resource_instance"
EXPERIMENT_TYPE = "experiment_type"
RESOURCE_TYPE   = "resource_type"

class ResourcesManager(object):
    def __init__(self, client_creator):
        self._client_creator = client_creator

    @typecheck(Resource)
    def add_resource(self, resource):
        client = self._client_creator()
        client.sadd(WEBLAB_RESOURCES, resource.resource_type)
        client.sadd(WEBLAB_RESOURCE % resource.resource_type, resource.resource_instance)
        
    @typecheck(ExperimentId, basestring)
    def add_experiment_id(self, experiment_id, resource_type):
        client = self._client_creator()
        client.sadd(WEBLAB_RESOURCES, resource_type)
        client.sadd(WEBLAB_EXPERIMENT_TYPES, experiment_id.to_weblab_str())
    
    @typecheck(basestring, ExperimentInstanceId, Resource)
    def add_experiment_instance_id(self, laboratory_coord_address, experiment_instance_id, resource):
        self.add_resource(resource)

        experiment_id     = experiment_instance_id.to_experiment_id()
        experiment_id_str = experiment_id.to_weblab_str()

        self.add_experiment_id(experiment_id, resource.resource_type)

        client = self._client_creator()
        client.sadd(WEBLAB_EXPERIMENT_INSTANCES % experiment_id_str, experiment_instance_id.inst_name)

        weblab_experiment_instance = WEBLAB_EXPERIMENT_INSTANCE % (experiment_id_str, experiment_instance_id.inst_name)

        weblab_resource_experiments = WEBLAB_RESOURCE_EXPERIMENTS % resource.resource_type
        client.sadd(weblab_resource_experiments, experiment_id_str)
        
        weblab_experiment_resources = WEBLAB_EXPERIMENT_RESOURCES % experiment_id_str
        client.sadd(weblab_experiment_resources, resource.resource_type)

        weblab_resource_instance_experiments = WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (resource.resource_type, resource.resource_instance)
        client.sadd(weblab_resource_instance_experiments, experiment_instance_id.to_weblab_str())

        retrieved_laboratory_coord_address = client.hget(weblab_experiment_instance, LAB_COORD)
        if retrieved_laboratory_coord_address is not None: 
            if retrieved_laboratory_coord_address != laboratory_coord_address:
                raise CoordExc.InvalidExperimentConfigError("Attempt to register the experiment %s in the laboratory %s; this experiment is already registered in the laboratory %s" % (experiment_instance_id, laboratory_coord_address, retrieved_laboratory_coord_address))

        client.hset(weblab_experiment_instance, LAB_COORD, laboratory_coord_address)

        retrieved_weblab_resource_instance = client.hget(weblab_experiment_instance, RESOURCE_INST)

        if retrieved_weblab_resource_instance is not None:
            if retrieved_weblab_resource_instance != resource.to_weblab_str():
                    raise CoordExc.InvalidExperimentConfigError("Attempt to register the experiment %s with resource %s when it was already bound to resource %s" % (experiment_instance_id, resource, retrieved_weblab_resource_instance))

        client.hset(weblab_experiment_instance, RESOURCE_INST, resource.to_weblab_str())

    def acquire_resource(self, session, current_resource_slot):
        # TODO: XXX: this makes no sense in redis

        slot_reservation = SchedulingSchemaIndependentSlotReservation(current_resource_slot)
        session.add(slot_reservation)
        return slot_reservation

    def release_resource(self, session, slot_reservation):
        session.delete(slot_reservation)

    def release_resource_instance(self, session, resource):
        # TODO: test me
        resource_instance = self._get_resource_instance(session, resource)
        slot = resource_instance.slot
        if slot is not None:
            slot_reservation = slot.slot_reservation
            if slot_reservation is not None:
                self.release_resource(session, slot_reservation)

    @typecheck(ExperimentId)
    def get_resource_types_by_experiment_id(self, experiment_id):
        client = self._client_creator()

        weblab_experiment_resources = WEBLAB_EXPERIMENT_RESOURCES % experiment_id.to_weblab_str()
        experiment_types = client.smembers(weblab_experiment_resources)
        if not client.exists(weblab_experiment_resources):
            raise CoordExc.ExperimentNotFoundError("Experiment not found: %s" % experiment_id)
        return set(experiment_types)

    def get_resource_instance_by_experiment_instance_id(self, experiment_instance_id):
        experiment_id = experiment_instance_id.to_experiment_id()
        weblab_experiment_instance = WEBLAB_EXPERIMENT_INSTANCE % (experiment_id.to_weblab_str(), experiment_instance_id.inst_name)

        client = self._client_creator()
        resource_instance = client.hget(weblab_experiment_instance, RESOURCE_INST)
        if resource_instance is None:
                raise CoordExc.ExperimentNotFoundError("Experiment not found: %s" % experiment_instance_id)

        return Resource.parse(resource_instance)

    def _get_resource_instance(self, session, resource):
        db_resource_type = session.query(ResourceType).filter_by(name = resource.resource_type).one()
        db_resource_instance = session.query(ResourceInstance).filter_by(name = resource.resource_instance, resource_type = db_resource_type).one()
        return db_resource_instance

    def mark_resource_as_broken(self, session, resource):
        db_resource_instance = self._get_resource_instance(session, resource)

        db_slot = db_resource_instance.slot
        if not db_slot is None:
            session.delete(db_slot)
            return True
        return False

    def mark_resource_as_fixed(self, resource):
        session = self._session_maker()
        try:
            db_resource_instance = self._get_resource_instance(session, resource)
    
            db_slot = db_resource_instance.slot
            if db_slot is None:
                db_slot = CurrentResourceSlot(db_resource_instance)
                session.add(db_slot)
                session.commit()
                return True
            return False
        finally:
            session.close()

    @typecheck(ExperimentInstanceId)
    def remove_resource_instance_id(self, experiment_instance_id):
        client = self._client_creator()

        experiment_id_str = experiment_instance_id.to_experiment_id().to_weblab_str()
        weblab_experiment_instances = WEBLAB_EXPERIMENT_INSTANCES % experiment_id_str
        weblab_experiment_instance  = WEBLAB_EXPERIMENT_INSTANCE % (experiment_id_str, experiment_instance_id.inst_name)

        resource_instance = client.hget(weblab_experiment_instance, RESOURCE_INST)
        if resource_instance is not None:
            # else it does not exist
            resource = Resource.parse(resource_instance)
            weblab_resource_experiment_instances = WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (resource.resource_type, resource.resource_instance)
            client.srem(weblab_experiment_instances, experiment_instance_id.inst_name)
            client.delete(weblab_experiment_instance)
            client.srem(weblab_resource_experiment_instances, experiment_instance_id.to_weblab_str())

    @typecheck(Resource)
    def remove_resource_instance(self, resource):
        client = self._client_creator()

        weblab_resource = WEBLAB_RESOURCE % resource.resource_type
        if client.srem(weblab_resource, resource.resource_instance):
            # else it did not exist
            weblab_resource_instance_experiments = WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (resource.resource_type, resource.resource_instance)
            experiment_instances = client.smembers(weblab_resource_instance_experiments) or []
            client.delete(weblab_resource_instance_experiments)
            for experiment_instance in experiment_instances:
                experiment_instance_id = ExperimentInstanceId.parse(experiment_instance)
                self.remove_resource_instance_id(experiment_instance_id)

    def list_resources(self):
        client = self._client_creator()
        return list(client.smembers(WEBLAB_RESOURCES))

    def list_resource_instances(self):
        client = self._client_creator()
        resource_instances = []
        for resource_type in client.smembers(WEBLAB_RESOURCES):
            for resource_instance in client.smembers(WEBLAB_RESOURCE % resource_type):
                resource_instances.append(Resource(resource_type, resource_instance))

        return resource_instances

    def list_experiments(self):
        client = self._client_creator()
        return [ ExperimentId.parse(exp_type) for exp_type in client.smembers(WEBLAB_EXPERIMENT_TYPES) ]

    @typecheck(ExperimentId)
    def list_experiment_instances_by_type(self, experiment_id):
        client = self._client_creator()
        weblab_experiment_instances = WEBLAB_EXPERIMENT_INSTANCES % experiment_id.to_weblab_str()
        return [ 
            ExperimentInstanceId(inst, experiment_id.exp_name, experiment_id.cat_name)
            for inst in client.smembers(weblab_experiment_instances) ]

    @typecheck(basestring)
    def list_experiment_instance_ids_by_resource_type(self, resource_type):
        client = self._client_creator()

        experiment_instance_ids = []

        instances = client.smembers(WEBLAB_RESOURCE % resource_type) or []
        for instance in instances:
            weblab_resource_instance_experiments = WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (resource_type, instance)
            current_members = client.smembers(weblab_resource_instance_experiments) or []
            for member in current_members:
                experiment_instance_id = ExperimentInstanceId.parse(member)
                experiment_instance_ids.append(experiment_instance_id)

        return experiment_instance_ids

    @typecheck(Resource)
    def list_experiment_instance_ids_by_resource(self, resource):
        client = self._client_creator()

        experiment_instance_ids = []

        weblab_resource_instance_experiments = WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (resource.resource_type, resource.resource_instance)
        current_members = client.smembers(weblab_resource_instance_experiments) or []
        for member in current_members:
            experiment_instance_id = ExperimentInstanceId.parse(member)
            experiment_instance_ids.append(experiment_instance_id)

        return experiment_instance_ids

    def list_laboratories_addresses(self):
        client = self._client_creator()

        laboratory_addresses = {
            # laboratory_coord_address : {
            #         experiment_instance_id : resource_instance
            # }
        }

        for experiment_type in client.smembers(WEBLAB_EXPERIMENT_TYPES):
            experiment_id = ExperimentId.parse(experiment_type)
            experiment_instance_names = client.smembers(WEBLAB_EXPERIMENT_INSTANCES % experiment_type)
            for experiment_instance_name in experiment_instance_names:
                experiment_instance_id = ExperimentInstanceId(experiment_instance_name, experiment_id.exp_name, experiment_id.cat_name)
                weblab_experiment_instance = WEBLAB_EXPERIMENT_INSTANCE % (experiment_type, experiment_instance_name)
                laboratory_address = client.hget(weblab_experiment_instance, LAB_COORD)
                resource_str       = client.hget(weblab_experiment_instance, RESOURCE_INST)
                resource           = Resource.parse(resource_str)
                current            = laboratory_addresses.get(laboratory_address, {})
                current[experiment_instance_id] = resource
                laboratory_addresses[laboratory_address] = current

        return laboratory_addresses

    @typecheck(basestring, ExperimentId, basestring)
    def associate_scheduler_to_reservation(self, reservation_id, experiment_id, resource_type_name):
        client = self._client_creator()

        reservations_active_schedulers = WEBLAB_RESERVATIONS_ACTIVE_SCHEDULERS % reservation_id

        serialized = json.dumps({ EXPERIMENT_TYPE : experiment_id.to_weblab_str(), RESOURCE_TYPE : resource_type_name })
        client.sadd(reservations_active_schedulers, serialized)

    def dissociate_scheduler_from_reservation(self, reservation_id, experiment_id, resource_type_name):
        client = self._client_creator()

        reservations_active_schedulers = WEBLAB_RESERVATIONS_ACTIVE_SCHEDULERS % reservation_id
        serialized = json.dumps({ EXPERIMENT_TYPE : experiment_id.to_weblab_str(), RESOURCE_TYPE : resource_type_name })

        client.srem(reservations_active_schedulers, serialized)

    def clean_associations_for_reservation(self, reservation_id, experiment_id):
        client = self._client_creator()
        reservations_active_schedulers = WEBLAB_RESERVATIONS_ACTIVE_SCHEDULERS % reservation_id
        client.delete(reservations_active_schedulers)

    def retrieve_schedulers_per_reservation(self, reservation_id, experiment_id):
        client = self._client_creator()

        reservations_active_schedulers = WEBLAB_RESERVATIONS_ACTIVE_SCHEDULERS % reservation_id
        
        associations = client.smembers(reservations_active_schedulers) or ()
        resource_type_names = []

        for member in associations:
            deserialized = json.loads(member)
            resource_type_names.append(deserialized[RESOURCE_TYPE])

        return resource_type_names

    def _clean(self):
        client = self._client_creator()
        for element in client.smembers(WEBLAB_RESOURCES):
            for instance in client.smembers(WEBLAB_RESOURCE % element):
                client.delete(WEBLAB_RESOURCE_INSTANCE_EXPERIMENTS % (element, instance))
            client.delete(WEBLAB_RESOURCE % element)
            client.delete(WEBLAB_RESOURCE_EXPERIMENTS % element)
        client.delete(WEBLAB_RESOURCES)

        for element in client.smembers(WEBLAB_EXPERIMENT_TYPES):
            client.delete(WEBLAB_EXPERIMENT_RESOURCES % element)
            for instance in client.smembers(WEBLAB_EXPERIMENT_INSTANCES % element):
                client.delete(WEBLAB_EXPERIMENT_INSTANCE % (element, instance))
            client.delete(WEBLAB_EXPERIMENT_INSTANCES % element)
        client.delete(WEBLAB_EXPERIMENT_TYPES)
