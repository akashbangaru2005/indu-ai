import React from "react";

import "./InduCore.css";


function InduCore({
  state = "idle",
  wake = false
}) {

  const statusText = {

    idle: "Ready",

    waking: "Waking up...",

    listening: "Listening...",

    thinking: "Thinking...",

    speaking: "Speaking..."

  };


  return (

    <section
      className={`
        indu-container
        ${state}
        ${wake ? "wake-active" : ""}
      `}
    >

      <div className="wake-pulse pulse-one"></div>

      <div className="wake-pulse pulse-two"></div>

      <div className="wake-pulse pulse-three"></div>


      <div className="indu-orb">

        <div className="ring ring-one"></div>

        <div className="ring ring-two"></div>

        <div className="ring ring-three"></div>


        <div className="indu-core">

          <div className="core-glow"></div>


          <div className="core-center">

            <span className="indu-symbol">
              I
            </span>

          </div>

        </div>

      </div>


      <h1 className="indu-name">
        INDU
      </h1>


      <p className="indu-status">
        {statusText[state] || "Ready"}
      </p>

    </section>

  );

}


export default InduCore;