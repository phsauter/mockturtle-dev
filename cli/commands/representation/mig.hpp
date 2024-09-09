/* mockturtle: C++ logic network library
 * Copyright (C) 2018-2024  EPFL
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use,
 * copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following
 * conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */

/*!
  \file mig.hpp
  \brief MIG command

  \author Alessandro tempia Calvino
*/

#pragma once

#include <alice/alice.hpp>

#include <mockturtle/algorithms/cleanup.hpp>
#include <mockturtle/views/names_view.hpp>

namespace alice
{

/* Writes a network to file */
class mig_command : public alice::command
{
public:
  explicit mig_command( const environment::ptr& env )
      : command( env,
                 "Converts the current Boolean network to an MIG." )
  {}

protected:
  void execute()
  {
    if ( store<network_manager>().empty() )
    {
      env->err() << "[e] Empty logic network.\n";
      return;
    }

    network_manager& ntk = store<network_manager>().current();
    if ( ntk.is_type( network_manager_type::AIG ) )
    {
      network_manager::aig_names& aig = ntk.get_aig();
      network_manager::mig_names mig = mockturtle::cleanup_dangling<network_manager::aig_names, network_manager::mig_names>( aig );
      ntk.load_mig( mig );
    }
    else if ( ntk.is_type( network_manager_type::XAG ) )
    {
      network_manager::xag_names& xag = ntk.get_xag();
      network_manager::mig_names mig = mockturtle::cleanup_dangling<network_manager::xag_names, network_manager::mig_names>( xag );
      ntk.load_mig( mig );
    }
    else if ( ntk.is_type( network_manager_type::MIG ) )
    {
      network_manager::mig_names& mig = ntk.get_mig();
      mig = mockturtle::cleanup_dangling( mig );
    }
    else if ( ntk.is_type( network_manager_type::XMG ) )
    {
      network_manager::xmg_names& xmg = ntk.get_xmg();
      network_manager::mig_names mig = mockturtle::cleanup_dangling<network_manager::xmg_names, network_manager::mig_names>( xmg );
      ntk.load_mig( mig );
    }
    else
    {
      env->err() << "[e] For other logic network types, run the strash command first.\n";
    }
  }

private:
  std::string filename{};
};

ALICE_ADD_COMMAND( mig, "Data structure" );

} // namespace alice