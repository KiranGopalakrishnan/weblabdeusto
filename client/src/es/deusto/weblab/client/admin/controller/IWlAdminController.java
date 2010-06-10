/*
* Copyright (C) 2005-2009 University of Deusto
* All rights reserved.
*
* This software is licensed as described in the file COPYING, which
* you should have received as part of this distribution.
*
* This software consists of contributions made by many individuals, 
* listed below:
*
* Author: FILLME
*
*/

package es.deusto.weblab.client.admin.controller;

import java.util.Date;

import es.deusto.weblab.client.admin.ui.IUIManager;
import es.deusto.weblab.client.dto.SessionID;
import es.deusto.weblab.client.dto.experiments.Experiment;
import es.deusto.weblab.client.dto.users.Group;

public interface IWlAdminController {
	
	void login(String username, String password);
	void startLoggedIn(SessionID sessionId);
	void logout();
	
	void getExperiments();
	void getGroups();
	void getExperimentUses(Date fromDate, Date toDate, Group group,	Experiment experiment);

	void setUIManager(IUIManager theme);
}
