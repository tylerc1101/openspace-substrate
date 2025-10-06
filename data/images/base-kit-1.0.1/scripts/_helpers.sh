prompt()
{
  local quiet=${QUIET_PROMPT}
  local quiet_print=0

  local complex=0
  if [ "$1" == "--complex" ]; then
    complex=1
    shift
  fi

  local silent=""
  if [ "$1" == "--silent" ]; then
    silent="-s"
    shift
  fi
  if [ "$1" == "--quiet-print" ]; then
    quiet_print=1
    shift
  fi
  local display="$1"
  local variable="$2"
  local default="$3"
  local choices="$4"
  local default_display
  local random_generated=0
  if [ -n "${silent}" ]; then
    # For silent prompts, if no default is given, generate a secure secret
    # value to use as the default.
    if [ -z "$default" ]; then
      if [ ${complex} -eq 0 ] ; then
        default=$(dd if=/dev/random bs=32 count=1 status=none | sha256sum | awk '{print $1}')
      else
        valid=0
        while [ ${valid} -eq 0 ] ; do
          # find a password with at least one lowercase, one uppercase, and one number
          default=$(dd if=/dev/random bs=32 count=1 status=none | sha256sum | base64 | awk '{print $1}' | head -n 1)
          upper=$(echo "${default}" | grep -c "[A-Z]")
          lower=$(echo "${default}" | grep -c "[a-z]")
          digit=$(echo "${default}" | grep -c "[0-9]")
          if [ "${upper}" != "0" ] && [ "${lower}" != "0" ] && [ "${upper}" != "0" ] ; then
            valid=1
          fi
        done
      fi
      default_display="(random generated password)"
      random_generated=1

      # passwords must be prompted for in update mode
      if [ "${quiet}" = "2" ] ; then
        quiet=
      fi
    else
      # Redact sensitive value, but still provide an indication that there is one.
      default_display=$(echo -n "$default" | tr '\000-\377' '*')
    fi
  else
    default_display="$default"
  fi
  valid=0

  retries=10
  while [ ${valid} -ne 1 ] ; do
    valid=1

    if [ -z "${quiet}" ] ; then
      read -r -p "${display} [${default_display}]: " ${silent} ${variable}
    else
      printf -v "${variable}" ""
    fi

    # handle non-empty
    if [ "${choices}" = "non-empty" ] || [ "${choices}" = "non-empty-file" ] ; then
      if [ "${!variable}" = "-" ] ; then
        valid=0
      elif [ "${!variable}" = "" ] && [ "${default}" = "" ] ; then
        valid=0
      fi
    fi
    if [ "${choices}" != "" ] && [ "${choices}" != "non-empty" ] && [ "${choices}" != "non-empty-file" ] ; then
      verifier="${!variable}"
      if [ "${verifier}" = "" ] ; then
        verifier="${default}"
      fi
      if [ "`echo \"${verifier}\" | grep -c -E \"^${choices}$\"`" != "1" ] ; then
        valid=0
      fi
    fi
    if [ "${choices}" = "non-empty-file" ] ; then
      if [ "${!variable}" = "" ] && [ "${default}" != "" ] ; then
        if [ ! -f "${default}" ] ; then
          echo "File (${default}) does not exist." >&2
          valid=0
        fi
      elif [ "${!variable}" != "" ] ; then
        if [ ! -f "${!variable}" ] ; then
          echo "File (${variable}) does not exist." >&2
          valid=0
        fi
      fi
    fi

    # handle confirmation for silent non-empty prompts
    if [ "${silent}" != "" ] ; then
      if [ "${!variable}" != "" ] ; then
        echo ""
        retype_variable="retype_${variable}"
        read -r -p "Retype ${display}: " ${silent} ${retype_variable}
        if [ "${!variable}" != "${!retype_variable}" ] ; then
          echo "Inputs do not match." >&2
          valid=0
        fi
      elif [ "${random_generated}" = "1" ] ; then
        valid_confirm=0
        retries_confirm=3

        if [ "${quiet}" = "" ] ; then
          echo ""
          while [ ${valid_confirm} -ne 1 ] ; do
            read -r -p "Display random generated value now [no]: " show_password
            if [ "${show_password}" = "no" ] || [ "${show_password}" = "" ] ; then
              valid_confirm=1
            elif [ "${show_password}" = "yes" ] ; then
              valid_confirm=1
              echo "${default}"
            else
              retries_confirm=$((retries_confirm-1))
              if [ "$retries_confirm" -gt 0 ] ; then
                echo "Invalid input. Try again." >&2
              else
                echo "Invalid input. Continuing." >&2
                valid_confirm=1
              fi
            fi
          done
        else
          quiet_print=1
        fi
      fi
    fi

    if [ ${valid} -eq 0 ] ; then
      retries=$((retries-1))
      if [ "$retries" -gt 0 ]; then
        if [ -z "${quiet}" ] ; then
          echo "Invalid input. Try again." >&2
        else
          echo "Required input must be provided." >&2
        fi
        quiet=
      else
        echo "Invalid input. Aborting." >&2
        exit 1
      fi
    fi
  done

  if [ "${!variable}" = "" ] ; then
    printf -v "${variable}" "%s" "${default}"
  elif [ "${!variable}" = "-" ] ; then
    # entry of - is treated as a blank
    printf -v "${variable}" "%s" ""
  fi
  # When using the non-echoing read, there is no newline displayed either, so
  # ensure we move to the next line.
  if [ -n "${silent}" ] && [ "${quiet}" = "" ] ; then
    echo ""
  fi

  # output value for quiet-print (not update)
  if [ ${quiet_print} -ne 0 ] && [ "${quiet}" = "1" ] ; then
    echo "${display}: ${!variable}"
  fi
}
