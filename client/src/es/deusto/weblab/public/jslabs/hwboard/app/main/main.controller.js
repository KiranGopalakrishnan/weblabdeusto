'use strict'

angular
    .module('hwboard')
    .controller('MainController', MainController);


function MainController($scope, $injector, $log) {
    var controller = this;

    // ---------------
    // Dependencies
    // ---------------
    // For some reason when we include $log through the injector
    // but it is not as an argument, it fails.
    statusUpdater = $injector.get("statusUpdater");


    // ---------------
    // Initialization
    // ---------------
    $log.debug("HW board experiment main controller");

    Weblab.setOnStartInteractionCallback(onStartInteraction);
    Weblab.setOnEndCallback(onEndInteraction);
    Weblab.setOnTimeCallback(onTime);


    // ----------------
    // Implementations
    // ----------------

    function onStartInteraction(config) {
        statusUpdater.start();
    } // !onStartInteraction

    function onEndInteraction() {
        statusUpdater.stop();
    } // !onEndInteraction

    function onTime(time) {
        $log.debug("TIME IS: " + time)
    } // !onTime

} // !MainController
